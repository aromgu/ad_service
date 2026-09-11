"""검수된 분석 결과와 승인 선택을 상세페이지 계획 요청으로 변환한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ad_service.api.schemas.detail_page_plan import (
    DetailPagePlanningRequest,
    ProductApprovalRequest,
)
from ad_service.api.schemas.product_analysis import ProductAnalysisResult
from ad_service.pipelines.product_approval import approve_product_analysis


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def run(analysis_path: Path, selection_path: Path, output: Path) -> Path:
    analysis = ProductAnalysisResult.model_validate_json(analysis_path.read_bytes())
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    planning = selection.pop("planning")
    approval = ProductApprovalRequest.model_validate(
        {**selection, "analysis": analysis.model_dump(mode="json")}
    )
    product = approve_product_analysis(approval)
    request = DetailPagePlanningRequest.model_validate(
        {**planning, "product": product.model_dump(mode="json")}
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "approval.json", approval.model_dump(mode="json"))
    write_json(output / "product.json", product.model_dump(mode="json"))
    write_json(output / "request.json", request.model_dump(mode="json"))
    return output / "request.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("완료:", run(args.analysis, args.selection, args.output))
