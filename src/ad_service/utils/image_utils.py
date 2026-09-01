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
    return ImageFont.truetype(selected or "DejaVuSans.ttf", size)


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
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = candidate
    if current:
        lines.append(current.rstrip())
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
