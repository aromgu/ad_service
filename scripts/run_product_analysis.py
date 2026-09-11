"""상품 분석 요청과 로컬 자산을 실제 모델에 한 번 전달하고 결과를 보존한다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from ad_service.api.schemas.product_analysis import ProductAnalysisRequest
from ad_service.models.product_analyzer import (
    INSTRUCTIONS,
    MODEL,
    PROMPT_VERSION,
    ImagePayload,
    analyze_product,
    response_schema,
)


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def load_asset(argument: str) -> tuple[str, Path, ImagePayload, tuple[int, int]]:
    asset_id, separator, raw_path = argument.partition("=")
    if not separator or not asset_id or not raw_path:
        raise ValueError("--asset은 asset_id=/path/image 형식이어야 합니다")
    path = Path(raw_path).expanduser().resolve()
    raw = path.read_bytes()
    with Image.open(path) as image:
        mime_type = Image.MIME.get(image.format or "")
        size = image.size
        image.verify()
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("JPEG, PNG, WEBP 이미지만 지원합니다")
    return asset_id, path, ImagePayload(raw, mime_type), size


def run(request_path: Path, assets: list[str], output: Path) -> Path:
    request = ProductAnalysisRequest.model_validate_json(request_path.read_bytes())
    loaded = [load_asset(argument) for argument in assets]
    payloads = {asset_id: payload for asset_id, _, payload, _ in loaded}
    if len(payloads) != len(loaded):
        raise ValueError("--asset의 asset_id가 중복되었습니다")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "request.json", request.model_dump(mode="json"))
    write_json(
        output / "execution.json",
        {
            "model": MODEL,
            "prompt_version": PROMPT_VERSION,
            "instructions": INSTRUCTIONS,
            "schema": response_schema(),
            "max_retries": 0,
            "assets": [
                {
                    "asset_id": asset_id,
                    "source_name": path.name,
                    "width": size[0],
                    "height": size[1],
                    "sha256": hashlib.sha256(payload.data).hexdigest(),
                }
                for asset_id, path, payload, size in loaded
            ],
        },
    )
    try:
        result = analyze_product(
            request,
            payloads,
            record_response=lambda value: write_json(output / "response.json", value),
        )
        write_json(output / "result.json", result.model_dump(mode="json"))
    except Exception as exc:
        write_json(
            output / "failure.json",
            {
                "status": "failed",
                "type": type(exc).__name__,
                "note": "자동 재시도·상품 정보 저장 없음. 입력과 원시 응답을 검토하세요.",
            },
        )
        raise
    return output / "result.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument(
        "--asset",
        action="append",
        required=True,
        help="요청의 asset_id와 파일 경로. 예: front=/data/front.jpg",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("완료:", run(args.request, args.asset, args.output))
