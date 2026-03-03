import os
import re
import base64
import time
import io
from pathlib import Path
from dotenv import load_dotenv

try:
    import requests
except ImportError:
    print("오류: pip install requests")
    exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("오류: pip install Pillow")
    exit(1)

# ─── 설정 ────────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent / ".env")
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("오류: .env 파일에서 GEMINI_API_KEY를 찾을 수 없습니다.")
    exit(1)

ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"imagen-4.0-generate-001:predict?key={api_key}"
)

TARGET_SIZE = (1200, 1200)

# 전체 프롬프트에 추가할 실사풍 접두사
PHOTO_PREFIX = (
    "Ultra-realistic professional photograph, shot on full-frame DSLR camera, "
    "cinematic natural lighting, sharp focus, no CGI, no illustration, no cartoon, "
    "no 3D render, real photograph, "
)

# 전체 이미지에 적용할 공통 네거티브 프롬프트
COMMON_NEGATIVE = (
    "cartoon, illustration, CGI, 3D render, animation, painting, drawing, anime, "
    "sketch, watercolor, digital art, unrealistic, low quality, blurry, distorted, "
    "watermark, logo, oversaturated, plastic, fake"
)

# Windows 한글 폰트 경로
FONT_PATHS = [
    "C:/Windows/Fonts/malgunbd.ttf",   # 맑은 고딕 Bold
    "C:/Windows/Fonts/malgun.ttf",     # 맑은 고딕
    "C:/Windows/Fonts/gulim.ttc",      # 굴림
]

# ─── 각 이미지별 한국어 카피 ─────────────────────────────
COPY = {
    "01": {
        "headline": "지금, 당신은 괜찮으신가요?",
        "sub":      "번아웃이 조용히 당신을 잠식하고 있습니다",
    },
    "02": {
        "headline": "주말에도 쉬지 못하나요?",
        "sub":      "멈출 수 없는 악순환에서 벗어날 시간입니다",
    },
    "03": {
        "headline": "빛이 있는 곳으로",
        "sub":      "제주 애월에서 시작되는 나만의 회복",
    },
    "04": {
        "headline": "제주야 애월 독서스테이",
        "sub":      "독채 민박 당신만을 위한 힐링 독서 프로그램",
    },
    "05": {
        "headline": "4가지 힐링 프로그램",
        "sub":      "싱잉볼 명상 · 계절 식탁 · 새벽 산책 · 독서노트",
    },
    "06": {
        "headline": "단 하룻밤이 모든 것을 바꿉니다",
        "sub":      "소진된 나  →  회복된 나",
    },
    "07": {
        "headline": "이미 다녀온 분들의 이야기",
        "sub":      "\"정말 다시 오고 싶어요\"  — 참가자 후기",
    },
    "08": {
        "headline": "프로그램 구성",
        "sub":      "금요일 저녁 6시 ~ 토요일 낮 12시 · 최대 6명",
    },
    "09": {
        "headline": "걱정은 내려두세요",
        "sub":      "자주 묻는 모든 질문에 답해드립니다",
    },
    "10": {
        "headline": "단돈 8만원",
        "sub":      "숙박 · 식사 · 명상 · 산책 · 독서 모두 포함",
    },
    "11": {
        "headline": "100% 만족 보장",
        "sub":      "마음에 들지 않으면 전액 환불해 드립니다",
    },
    "12": {
        "headline": "단 8자리 한정",
        "sub":      "마지막 1자리 남았습니다 · 지금 바로 신청하세요",
    },
    "13": {
        "headline": "당신도 이렇게 될 수 있습니다",
        "sub":      "지금 바로 신청하기  →",
    },
}


# ─── 유틸 함수 ───────────────────────────────────────────
def get_font(size: int):
    for path in FONT_PATHS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def add_text_overlay(img: Image.Image, image_num: str) -> Image.Image:
    """이미지 하단에 반투명 그라디언트 + 한국어 카피 텍스트를 오버레이한다."""
    copy = COPY.get(image_num, {})
    headline = copy.get("headline", "")
    sub      = copy.get("sub", "")
    if not headline:
        return img

    w, h = img.size
    overlay = img.copy().convert("RGBA")

    # ── 하단 그라디언트 오버레이 ──────────────────────────
    gradient_h = int(h * 0.38)        # 하단 38% 영역
    gradient = Image.new("RGBA", (w, gradient_h), (0, 0, 0, 0))
    draw_grad = ImageDraw.Draw(gradient)
    for y in range(gradient_h):
        alpha = int(210 * (y / gradient_h))   # 위→아래로 점점 진하게
        draw_grad.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    overlay.paste(gradient, (0, h - gradient_h), gradient)

    # ── 텍스트 그리기 ─────────────────────────────────────
    draw = ImageDraw.Draw(overlay)

    headline_size = int(w * 0.058)    # 약 70px (1200px 기준)
    sub_size      = int(w * 0.033)    # 약 40px

    font_headline = get_font(headline_size)
    font_sub      = get_font(sub_size)

    padding     = int(w * 0.055)      # 좌우·하단 여백
    line_gap    = int(h * 0.018)      # 헤드라인↔서브 간격

    # 서브텍스트 위치 (하단에서 padding 위)
    sub_bbox = draw.textbbox((0, 0), sub, font=font_sub)
    sub_h = sub_bbox[3] - sub_bbox[1]
    sub_y = h - padding - sub_h

    # 헤드라인 위치 (서브텍스트 위)
    hl_bbox = draw.textbbox((0, 0), headline, font=font_headline)
    hl_h = hl_bbox[3] - hl_bbox[1]
    hl_y = sub_y - line_gap - hl_h

    # 텍스트 그림자 (가독성 향상)
    shadow_offset = 2
    draw.text((padding + shadow_offset, hl_y + shadow_offset), headline,
              font=font_headline, fill=(0, 0, 0, 160))
    draw.text((padding + shadow_offset, sub_y + shadow_offset), sub,
              font=font_sub, fill=(0, 0, 0, 140))

    # 본문 텍스트
    draw.text((padding, hl_y), headline, font=font_headline, fill=(255, 255, 255, 255))
    draw.text((padding, sub_y), sub,      font=font_sub,      fill=(220, 220, 220, 230))

    return overlay.convert("RGB")


def generate_image(prompt: str, negative: str, image_num: str,
                   output_dir: Path, max_retries: int = 3) -> bool:
    output_path = output_dir / f"image_{image_num}.png"

    full_prompt   = PHOTO_PREFIX + prompt
    full_negative = COMMON_NEGATIVE + (", " + negative if negative else "")

    payload = {
        "instances": [{"prompt": full_prompt, "negativePrompt": full_negative}],
        "parameters": {"sampleCount": 1, "aspectRatio": "1:1"},
    }

    for attempt in range(1, max_retries + 1):
        try:
            print(f"  [시도 {attempt}/{max_retries}] API 호출 중...")
            response = requests.post(ENDPOINT, json=payload, timeout=90)
            data = response.json()

            if "error" in data:
                msg = data["error"].get("message", str(data["error"]))
                print(f"  API 오류: {msg}")
                if attempt < max_retries:
                    time.sleep(5)
                continue

            b64      = data["predictions"][0]["bytesBase64Encoded"]
            img_bytes = base64.b64decode(b64)

            # 1200x1200 리사이즈
            img = Image.open(io.BytesIO(img_bytes))
            img = img.resize(TARGET_SIZE, Image.LANCZOS)

            # 한국어 텍스트 오버레이
            img = add_text_overlay(img, image_num)

            img.save(output_path, "PNG")
            print(f"  저장 완료: {output_path} ({TARGET_SIZE[0]}x{TARGET_SIZE[1]}px, 텍스트 오버레이 포함)")
            return True

        except Exception as e:
            print(f"  예외 발생: {e}")
            if attempt < max_retries:
                time.sleep(5)

    print(f"  실패: {max_retries}회 모두 실패")
    return False


def parse_prompts(prompts_file: Path) -> list:
    content  = prompts_file.read_text(encoding="utf-8")
    sections = re.split(r"(?=## 이미지 \d+)", content)
    results  = []

    for section in sections:
        if "## 이미지" not in section:
            continue

        num_match = re.search(r"## 이미지 (\d+)", section)
        if not num_match:
            continue
        num = num_match.group(1).zfill(2)

        prompt_match = re.search(r"```\n(.*?)\n```", section, re.DOTALL)
        prompt = prompt_match.group(1).strip() if prompt_match else ""

        neg_match = re.search(r"\*\*네거티브 프롬프트\*\*:\s*(.+)", section)
        negative  = neg_match.group(1).strip() if neg_match else ""

        results.append((num, prompt, negative))

    return results


# ─── 메인 ────────────────────────────────────────────────
if __name__ == "__main__":
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    prompts_file = Path("prompts.md")
    if not prompts_file.exists():
        print("오류: prompts.md가 없습니다.")
        exit(1)

    prompts = parse_prompts(prompts_file)
    if not prompts:
        print("오류: prompts.md에서 프롬프트를 파싱할 수 없습니다.")
        exit(1)

    print(f"총 {len(prompts)}개 프롬프트 로드 완료")
    print(f"출력 크기: {TARGET_SIZE[0]}x{TARGET_SIZE[1]}px · 한국어 텍스트 오버레이 포함\n")

    failed = []
    for i, (num, prompt, negative) in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] 이미지 {num} 생성 중...")
        success = generate_image(prompt, negative, num, output_dir)
        if not success:
            failed.append(num)
        if i < len(prompts):
            time.sleep(3)

    print(f"\n=== 생성 완료 ===")
    print(f"성공: {len(prompts) - len(failed)}/{len(prompts)}개")
    if failed:
        print(f"실패한 이미지: {', '.join(failed)}")
    else:
        print("모든 이미지 생성 성공!")
        print(f"저장 위치: {output_dir.resolve()}")
