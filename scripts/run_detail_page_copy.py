"""승인된 상세페이지 계획으로 한국어 카피 모델을 한 번 실행한다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ad_service.api.schemas.detail_page_copy import DetailPageCopyRequest
from ad_service.models.detail_page_copywriter import (
    INSTRUCTIONS,
    MAX_OUTPUT_TOKENS,
    MODEL,
    PROMPT_VERSION,
    response_schema,
    write_detail_page_copy,
)


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def run(request_path: Path, output: Path) -> Path:
    request = DetailPageCopyRequest.model_validate_json(request_path.read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "request.json", request.model_dump(mode="json"))
    write_json(
        output / "execution.json",
        {
            "model": MODEL,
            "prompt_version": PROMPT_VERSION,
            "instructions": INSTRUCTIONS,
            "schema": response_schema(),
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_retries": 0,
            "note": "이미지 분석·생성·HTML 렌더링·영구 저장은 실행하지 않습니다.",
        },
    )
    emitted = []
    try:
        result = write_detail_page_copy(
            request,
            record_response=lambda value: write_json(output / "response.json", value),
            on_event=lambda event: emitted.append(event.model_dump(mode="json")),
        )
        write_json(output / "events.json", {"events": emitted})
        write_json(output / "result.json", result.model_dump(mode="json"))
    except Exception as exc:
        write_json(output / "events.json", {"events": emitted})
        write_json(
            output / "failure.json",
            {
                "status": "failed",
                "type": type(exc).__name__,
                "note": "자동 재시도·이미지 생성·문서 저장 없음. 원시 응답을 검토하세요.",
            },
        )
        raise
    return output / "result.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("완료:", run(args.request, args.output))
