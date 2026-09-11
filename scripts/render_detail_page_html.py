"""카피 또는 챗봇 수정 결과를 독립 실행 가능한 긴 상세페이지 HTML로 내보낸다."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

from ad_service.api.schemas.revision import EditableDocument
from ad_service.pipelines.revision import document_hash
from ad_service.rendering.detail_page_html import render_detail_page_html

ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _document(payload: dict) -> EditableDocument:
    if "preview" in payload:
        value = payload["preview"]["document"]
    elif "document" in payload:
        value = payload["document"]
    else:
        value = payload
    return EditableDocument.model_validate(value)


def _asset_arguments(values: list[str]) -> dict[str, Path]:
    result = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--asset은 asset_id=/절대/경로 형식이어야 합니다")
        asset_id, raw_path = value.split("=", 1)
        if not asset_id or asset_id in result:
            raise ValueError("이미지 asset_id가 비어 있거나 중복되었습니다")
        result[asset_id] = Path(raw_path).expanduser().resolve()
    return result


def run(result_path: Path, assets: dict[str, Path], output: Path) -> Path:
    raw = result_path.read_bytes()
    document = _document(json.loads(raw))
    known_assets = {asset.asset_id: asset for asset in document.assets}
    if set(assets) != set(known_assets):
        raise ValueError("문서 자산과 --asset 매핑이 정확히 일치해야 합니다")
    asset_urls = {}
    asset_manifest = []
    prepared_assets = []
    for asset_id, source in assets.items():
        if source.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES or not source.is_file():
            raise ValueError(f"지원하지 않거나 찾을 수 없는 이미지입니다: {source}")
        if source.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("이미지는 파일당 20MB 이하여야 합니다")
        with Image.open(source) as image:
            image.verify()
        with Image.open(source) as image:
            width, height = image.size
        expected = known_assets[asset_id]
        if (width, height) != (expected.width, expected.height):
            raise ValueError(f"이미지 크기가 문서 메타데이터와 다릅니다: {asset_id}")
        filename = f"{asset_id}{source.suffix.lower()}"
        asset_urls[asset_id] = f"assets/{filename}"
        prepared_assets.append((source, filename))
        asset_manifest.append(
            {
                "asset_id": asset_id,
                "filename": filename,
                "width": width,
                "height": height,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )
    html = render_detail_page_html(document, asset_urls)
    output.mkdir(parents=True, exist_ok=False)
    asset_dir = output / "assets"
    asset_dir.mkdir()
    for source, filename in prepared_assets:
        shutil.copy2(source, asset_dir / filename)
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / "document.json").write_text(
        json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "source_result_sha256": hashlib.sha256(raw).hexdigest(),
                "document_sha256": document_hash(document),
                "document_id": document.document_id,
                "revision": document.revision,
                "model_calls": 0,
                "image_generation_calls": 0,
                "persisted": False,
                "assets": asset_manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output / "index.html"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("완료:", run(args.result, _asset_arguments(args.asset), args.output))
