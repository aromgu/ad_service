"""저장된 모델 응답을 추가 API 호출 없이 다시 검증하고 문서로 조립한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ad_service.api.schemas.detail_page_copy import (
    CopyStageEvent,
    DetailPageCopyMetrics,
    DetailPageCopyModelOutput,
    DetailPageCopyRequest,
    DetailPageCopyResult,
)
from ad_service.models.detail_page_copywriter import (
    MAX_OUTPUT_TOKENS,
    MODEL,
    validate_and_assemble_detail_page_copy,
)
from ad_service.models.vlm import TEXT_PRICES_PER_MILLION


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def extract_output_text(response: dict) -> str:
    values = [
        content["text"]
        for item in response.get("output", [])
        for content in item.get("content", [])
        if content.get("type") == "output_text"
    ]
    if len(values) != 1:
        raise ValueError("저장된 응답에서 단일 output_text를 찾을 수 없습니다")
    return values[0]


def run(source: Path, result_name: str, audit_name: str) -> Path:
    request = DetailPageCopyRequest.model_validate_json((source / "request.json").read_bytes())
    response = json.loads((source / "response.json").read_text(encoding="utf-8"))
    prior_events = json.loads((source / "events.json").read_text(encoding="utf-8"))[
        "events"
    ]
    output = DetailPageCopyModelOutput.model_validate_json(extract_output_text(response))
    document = validate_and_assemble_detail_page_copy(request, output)

    generation_events = [event for event in prior_events if event["stage"] != "result_validation"]
    elapsed_ms = max((event["elapsed_ms"] for event in generation_events), default=0)
    messages = [
        ("document_assembly", "started", "저장된 1회 응답으로 문서 조립을 시작합니다."),
        ("document_assembly", "completed", "편집 가능한 블록 문서를 조립했습니다."),
        ("result_validation", "completed", "수정된 규칙으로 저장 응답을 재검증했습니다."),
    ]
    events = [CopyStageEvent.model_validate(event) for event in generation_events]
    events.extend(
        CopyStageEvent(
            sequence=len(events) + index,
            stage=stage,
            status=status,
            elapsed_ms=elapsed_ms,
            message=message,
        )
        for index, (stage, status, message) in enumerate(messages, start=1)
    )

    usage = response.get("usage", {})
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    input_price, output_price = TEXT_PRICES_PER_MILLION.get(MODEL, (0.0, 0.0))
    estimated_cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    input_text = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    ceiling = (
        len(input_text) * input_price + MAX_OUTPUT_TOKENS * output_price
    ) / 1_000_000
    result = DetailPageCopyResult(
        request_id=request.request_id,
        document=document,
        events=events,
        warnings=list(output.warnings)
        + [
            "초기 검증 규칙의 이미지 근거 예외 누락을 수정한 뒤 동일 응답을 재검증했습니다.",
            "사람 검수 전 편집 문서이며 이미지·HTML 생성과 영구 저장은 실행하지 않았습니다.",
        ],
        metrics=DetailPageCopyMetrics(
            model=MODEL,
            latency_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost,
            preflight_cost_ceiling_usd=ceiling,
            response_id=response["id"],
        ),
    )
    write_json(
        source / audit_name,
        {
            "api_calls": 0,
            "source_response_id": response["id"],
            "reason": "이미지 전용 갤러리 본문은 source_asset_ids를 근거로 사용할 수 있게 수정",
            "preserved_initial_failure": ["events.json", "failure.json"],
        },
    )
    result_path = source / result_name
    write_json(result_path, result.model_dump(mode="json"))
    return result_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--result-name", default="result.json")
    parser.add_argument("--audit-name", default="revalidation.json")
    args = parser.parse_args()
    print("완료:", run(args.source, args.result_name, args.audit_name))
