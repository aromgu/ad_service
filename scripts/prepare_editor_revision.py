"""상세페이지 카피 결과와 사용자 지시를 챗봇 수정 요청으로 묶는다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ad_service.api.schemas.detail_page_copy import DetailPageCopyResult
from ad_service.models.revision_planner import PlanningRequest


def run(copy_result_path: Path, settings_path: Path, output_path: Path) -> Path:
    copy_result = DetailPageCopyResult.model_validate_json(copy_result_path.read_bytes())
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    request = PlanningRequest.model_validate(
        {**settings, "document": copy_result.document.model_dump(mode="json")}
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as file:
        json.dump(request.model_dump(mode="json"), file, ensure_ascii=False, indent=2)
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy-result", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("완료:", run(args.copy_result, args.settings, args.output))
