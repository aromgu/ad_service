from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ad_service.api.schemas.generation import AssetType, CopyResult, SafeArea

ASSET_SIZES = {
    AssetType.BANNER: (1536, 1024),
    AssetType.DETAIL_VISUAL: (1024, 1536),
    AssetType.PRODUCT_IMAGE: (1024, 1024),
}


def find_korean_font() -> str | None:
    candidates = [
        "/Library/Fonts/NotoSansKR-Regular.otf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf",
    ]
    return next((path for path in candidates if Path(path).exists()), None)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    regular = find_korean_font()
    bold_candidates = [
        "/Library/Fonts/NotoSansKR-Bold.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    selected = next((path for path in bold_candidates if bold and Path(path).exists()), regular)
    if selected is not None:
        return ImageFont.truetype(selected, size)

    # 개발 환경에 한글 글꼴이 빠져 있어도 전체 생성 작업이 중단되지는 않게 합니다.
    # 배포 Docker에는 fonts-noto-cjk를 설치하므로 실제 한글 미리보기는 Noto Sans를 씁니다.
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def _fit_product(cutout: Image.Image, max_width: int, max_height: int) -> Image.Image:
    product = cutout.copy()
    product.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    return product


def _product_position(
    asset_type: AssetType,
    canvas: Image.Image,
    product: Image.Image,
) -> tuple[int, int]:
    if asset_type is AssetType.BANNER:
        return (int(canvas.width * 0.70 - product.width / 2), canvas.height - product.height - 55)
    if asset_type is AssetType.DETAIL_VISUAL:
        return ((canvas.width - product.width) // 2, int(canvas.height * 0.30))
    return ((canvas.width - product.width) // 2, (canvas.height - product.height) // 2)


def compose_product(
    background: Image.Image,
    cutout: Image.Image,
    asset_type: AssetType,
) -> tuple[Image.Image, SafeArea | None]:
    canvas = background.convert("RGBA")
    if asset_type is AssetType.BANNER:
        max_size = (int(canvas.width * 0.43), int(canvas.height * 0.82))
        safe_area = SafeArea(x=70, y=90, width=int(canvas.width * 0.46), height=700)
    elif asset_type is AssetType.DETAIL_VISUAL:
        max_size = (int(canvas.width * 0.68), int(canvas.height * 0.52))
        safe_area = SafeArea(x=80, y=70, width=canvas.width - 160, height=300)
    else:
        max_size = (int(canvas.width * 0.70), int(canvas.height * 0.72))
        safe_area = None
    product = _fit_product(cutout, *max_size)
    x, y = _product_position(asset_type, canvas, product)
    shadow_alpha = product.getchannel("A").filter(
        ImageFilter.GaussianBlur(max(8, canvas.width // 80))
    )
    shadow = Image.new("RGBA", product.size, (20, 20, 20, 0))
    shadow.putalpha(shadow_alpha.point(lambda value: int(value * 0.24)))
    canvas.alpha_composite(shadow, (x + 18, y + 22))
    canvas.alpha_composite(product, (x, y))
    return canvas, safe_area


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """광고 문구를 단어 경계에 맞춰 여러 줄로 나눕니다.

    한국어도 띄어쓰기 단위로 먼저 배치해야 ``스 / 틱과자``처럼 한 단어가 어색하게
    갈라지지 않습니다. 단어 하나가 영역보다 긴 예외에만 글자 단위 분리를 사용합니다.
    """

    lines: list[str] = []
    current = ""

    def width(value: str) -> int:
        box = draw.textbbox((0, 0), value, font=font)
        return box[2] - box[0]

    for word in text.split():
        candidate = f"{current} {word}".strip()
        if not current or width(candidate) <= max_width:
            current = candidate
            continue

        lines.append(current)
        current = ""

        # 정상적인 광고 문구는 여기까지 오지 않습니다. URL처럼 공백이 없는 긴 문자열도
        # 영역 밖으로 넘치지 않도록 이 경우에만 글자 단위로 안전하게 나눕니다.
        if width(word) > max_width:
            chunk = ""
            for char in word:
                candidate = chunk + char
                if chunk and width(candidate) > max_width:
                    lines.append(chunk)
                    chunk = char
                else:
                    chunk = candidate
            current = chunk
        else:
            current = word

    if current:
        lines.append(current)
    return lines


def render_korean_copy(
    image: Image.Image,
    copy: CopyResult,
    asset_type: AssetType,
    safe_area: SafeArea | None,
) -> Image.Image:
    if safe_area is None or asset_type is AssetType.PRODUCT_IMAGE:
        return image.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    headline_font = _font(66 if asset_type is AssetType.BANNER else 56, bold=True)
    body_font = _font(30 if asset_type is AssetType.BANNER else 28)
    cta_font = _font(28, bold=True)
    x, y = safe_area.x, safe_area.y
    for line in _wrap(draw, copy.headline_candidates[0], headline_font, safe_area.width):
        draw.text((x, y), line, font=headline_font, fill=(30, 30, 36, 255))
        y += int(headline_font.size * 1.2)
    y += 25
    for line in _wrap(draw, copy.body_candidates[0], body_font, safe_area.width):
        draw.text((x, y), line, font=body_font, fill=(55, 55, 62, 235))
        y += int(body_font.size * 1.45)
    y += 30
    cta = copy.cta_candidates[0]
    text_box = draw.textbbox((0, 0), cta, font=cta_font)
    button_width = text_box[2] + 70
    button_height = text_box[3] - text_box[1] + 34
    draw.rounded_rectangle(
        (x, y, x + button_width, y + button_height),
        radius=button_height // 2,
        fill=(35, 35, 42, 240),
    )
    draw.text((x + 35, y + 13), cta, font=cta_font, fill=(255, 255, 255, 255))
    return image.convert("RGB")
