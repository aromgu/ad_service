"""승인된 상세페이지 계획과 상품 정보를 실제 카피 생성 요청으로 묶는다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ad_service.api.schemas.detail_page import ProductInput
from ad_service.api.schemas.detail_page_copy import DetailPageCopyRequest
from ad_service.api.schemas.detail_page_plan import DetailPagePlanResult


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def run(plan_path: Path, product_path: Path, settings_path: Path, output: Path) -> Path:
    plan = DetailPagePlanResult.model_validate_json(plan_path.read_bytes())
    product = ProductInput.model_validate_json(product_path.read_bytes())
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    request = DetailPageCopyRequest.model_validate(
        {
            **settings,
            "product": product.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
        }
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "request.json", request.model_dump(mode="json"))
    return output / "request.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("완료:", run(args.plan, args.product, args.settings, args.output))
