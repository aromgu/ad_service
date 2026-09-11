"""저장된 레이어만 사용하는 광고 결과 편집기. 모델을 호출하지 않습니다."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ad_service.api.schemas.editor import EditorScene, ProductPlacement, TextPlacement
from ad_service.api.schemas.generation import AssetType, GenerationResult
from ad_service.utils.image_utils import _font, _wrap


def local_file(run_dir: Path, filename: str) -> Path:
    """메타데이터의 절대 경로를 신뢰하지 않고 해당 실행 폴더 안의 파일만 읽습니다."""
    path = (run_dir / filename).resolve()
    if path.parent != run_dir.resolve() or not path.is_file():
        raise FileNotFoundError("편집에 필요한 결과 파일을 찾을 수 없습니다.")
    return path


def load_layers(run_dir: Path, kind: AssetType):
    result = GenerationResult.model_validate_json(local_file(run_dir, "result.json").read_text())
    asset = next((item for item in result.assets if item.type == kind), None)
    if asset is None:
        raise FileNotFoundError("해당 종류의 생성 결과가 없습니다.")
    direct = asset.details.get("input_strategy") == "direct_edit"
    suffix = "reference_edit" if direct else "background"
    with Image.open(local_file(run_dir, f"{kind.value}_{suffix}.png")) as source:
        if source.width > 4096 or source.height > 4096:
            raise ValueError("편집기는 가로·세로 4096px 이하의 결과를 지원합니다.")
        background = source.convert("RGBA")
    cutout = None
    if not direct and (run_dir / "product_cutout.png").exists():
        with Image.open(local_file(run_dir, "product_cutout.png")) as source:
            cutout = source.convert("RGBA")
    return result, asset, background, cutout


def default_scene(result, kind: AssetType, background: Image.Image, cutout) -> EditorScene:
    width, height = background.size
    scale = {AssetType.BANNER: 0.82, AssetType.DETAIL_VISUAL: 0.52}.get(kind, 0.72)
    product = ProductPlacement(height=scale)
    if cutout is not None:
        max_width = width * (0.43 if kind == AssetType.BANNER else 0.68)
        ratio = min(max_width / cutout.width, height * scale / cutout.height, 1)
        pw, ph = cutout.width * ratio, cutout.height * ratio
        product.height = ph / height
        if kind == AssetType.BANNER:
            product.x = min(1, max(0, (width * 0.70 - pw / 2) / max(1, width - pw)))
            product.y = max(0, 1 - 55 / max(1, height - ph))
        elif kind == AssetType.DETAIL_VISUAL:
            product.y = min(1, height * 0.30 / max(1, height - ph))
    copy = result.copy_result
    text = TextPlacement(
        visible=copy is not None and kind != AssetType.PRODUCT_IMAGE,
        headline=copy.headline_candidates[0] if copy else "",
        body=copy.body_candidates[0] if copy else "",
        cta=copy.cta_candidates[0] if copy else "",
        x=(70 if kind == AssetType.BANNER else 80) / width,
        y=(90 if kind == AssetType.BANNER else 70) / height,
        width=0.46 if kind == AssetType.BANNER else (width - 160) / width,
        headline_size=66 if kind == AssetType.BANNER else 56,
        body_size=30 if kind == AssetType.BANNER else 28,
    )
    # 작은 원본 상품도 입력 스키마 범위 안에서 다시 열 수 있어야 합니다.
    product.height = max(0.1, product.height)
    return EditorScene(product=product, text=text)


def render_scene(background: Image.Image, cutout, scene: EditorScene) -> Image.Image:
    canvas = background.copy().convert("RGBA")
    width, height = canvas.size
    if cutout is not None:
        placement = scene.product
        factor = min(height * placement.height / cutout.height, width * 0.95 / cutout.width)
        product = cutout.resize(
            (max(1, round(cutout.width * factor)), max(1, round(cutout.height * factor))),
            Image.Resampling.LANCZOS,
        )
        x = round((width - product.width) * placement.x)
        y = round((height - product.height) * placement.y)
        if placement.shadow:
            # 여백을 둔 별도 레이어로 그림자 가장자리가 상품 경계에서 잘리지 않게 합니다.
            alpha = Image.new("L", canvas.size)
            alpha.paste(product.getchannel("A"), (x + 18, y + 22))
            alpha = alpha.filter(ImageFilter.GaussianBlur(max(8, width // 80)))
            shadow = Image.new("RGBA", canvas.size, (20, 20, 20, 0))
            shadow.putalpha(alpha.point(lambda value: int(value * placement.shadow)))
            canvas = Image.alpha_composite(canvas, shadow)
        canvas.alpha_composite(product, (x, y))

    text = scene.text
    if not text.visible:
        return canvas.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    x, y = round(width * text.x), round(height * text.y)
    available_width = min(round(width * text.width), width - x - 12)
    for value, size, bold, spacing in (
        (text.headline, text.headline_size, True, 1.2),
        (text.body, text.body_size, False, 1.45),
    ):
        if not value.strip():
            continue
        font = _font(size, bold=bold)
        for paragraph in value.splitlines():
            for line in _wrap(draw, paragraph, font, available_width) or [""]:
                if y + size * spacing > height - 12:
                    raise ValueError("문구가 이미지 아래로 넘칩니다. 크기나 위치를 조절하세요.")
                draw.text((x, y), line, font=font, fill=text.color)
                y += round(size * spacing)
        y += 25
    if text.cta.strip():
        font = _font(28, bold=True)
        box = draw.textbbox((0, 0), text.cta, font=font)
        bw, bh = box[2] - box[0] + 70, box[3] - box[1] + 34
        if bw > available_width or y + bh > height - 12:
            raise ValueError("구매 버튼이 영역을 벗어납니다. 문구를 줄이거나 위치를 조절하세요.")
        draw.rounded_rectangle((x, y, x + bw, y + bh), radius=bh // 2, fill=text.color)
        draw.text((x + 35 - box[0], y + 17 - box[1]), text.cta, font=font, fill="white")
    return canvas.convert("RGB")


def saved_scene(path: Path) -> EditorScene:
    return EditorScene.model_validate(json.loads(path.read_text(encoding="utf-8"))["scene"])
