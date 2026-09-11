"""명시한 요청 파일로 계획 모델을 한 번 호출하고 증거와 미리보기 JSON을 저장한다."""

import argparse
import hashlib
import json
from pathlib import Path

from ad_service.models.revision_planner import (
    INSTRUCTIONS,
    MAX_OUTPUT_TOKENS,
    MODEL,
    PROMPT_VERSION,
    PlanningRequest,
    allowed_operation_types,
    plan_revision,
    response_schema,
)


def run(request_path: Path, output: Path):
    raw = request_path.read_bytes()
    request = PlanningRequest.model_validate_json(raw)
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        with (output / name).open("x", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)

    save("request.json", request.model_dump(mode="json"))
    save(
        "execution.json",
        {
            "model": MODEL,
            "prompt_version": PROMPT_VERSION,
            "instructions": INSTRUCTIONS,
            "schema": response_schema(
                allowed_operation_types(request.instruction), request.document
            ),
            "request_sha256": hashlib.sha256(raw).hexdigest(),
            "max_repair_attempts": 1,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "image_generation_calls": 0,
        },
    )
    responses: list[dict] = []

    def record(response: dict) -> None:
        # 보정 재시도가 붙으면 응답이 여러 번 온다. 호출 순서대로 남기고
        # 마지막 응답을 response.json 으로 둬서 채점 스크립트가 그대로 읽게 한다.
        responses.append(response)
        save(f"response_{len(responses)}.json", response)

    try:
        result = plan_revision(request, record_response=record)
        save("response.json", responses[-1])
        save("result.json", result.model_dump(mode="json"))
        print(
            json.dumps(
                {
                    "request_id": request.request_id,
                    "decision": result.proposal.decision,
                    "question": result.proposal.question,
                    "operations": [
                        op.model_dump(exclude_none=True) for op in result.proposal.operations
                    ],
                    "latency_ms": result.latency_ms,
                    "usage": result.usage,
                    "estimated_cost_usd": result.estimated_cost_usd,
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        if responses:
            save("response.json", responses[-1])
        save(
            "failure.json",
            {
                "type": type(exc).__name__,
                "model_calls": len(responses),
                "note": "실패/미완료 응답을 검토하세요. 보정 재시도 1회까지, 문서 변경 없음.",
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.request, args.output)
