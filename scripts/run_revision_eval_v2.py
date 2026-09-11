"""평가셋 전체를 순서대로 실행한다. 누적 비용 상한을 넘으면 즉시 멈춘다.

한 사례가 실패해도 나머지를 계속 실행하고 폴더에 failure.json 을 남긴다.
--dry-run 으로 먼저 호출 계획과 예상 비용만 확인할 수 있다 (모델 호출 0회).
"""

import argparse
import json
from pathlib import Path

from run_revision_experiment import run

from ad_service.models.revision_planner import (
    MODEL,
    PROMPT_VERSION,
    PlanningRequest,
    allowed_operation_types,
    response_schema,
)
from ad_service.models.vlm import TEXT_PRICES_PER_MILLION

# 9/10 실험의 건당 실측치. 예상 비용을 가늠하는 데만 쓴다.
TYPICAL_INPUT_TOKENS = 3700
TYPICAL_OUTPUT_TOKENS = 290


def case_names(requests: Path) -> list[str]:
    return sorted(
        path.stem for path in requests.glob("*.json") if path.stem != "expectations"
    )


def estimate_usd(count: int, repair_ratio: float = 0.2) -> float:
    """보정 재시도를 일부 감안한 대략적인 상한 추정치."""
    input_price, output_price = TEXT_PRICES_PER_MILLION.get(MODEL, (0.0, 0.0))
    per_call = (
        TYPICAL_INPUT_TOKENS * input_price + TYPICAL_OUTPUT_TOKENS * output_price
    ) / 1_000_000
    return per_call * count * (1 + repair_ratio)


def failed_case_cost(folder: Path) -> float:
    """검증에 실패한 사례의 실제 호출 비용도 누적한다.

    response.json은 마지막 response_N.json의 복사본이므로 숫자가 붙은
    원시 응답만 합산해 중복 계산을 막는다.
    """
    input_price, output_price = TEXT_PRICES_PER_MILLION.get(MODEL, (0.0, 0.0))
    total = 0.0
    for path in folder.glob("response_[0-9]*.json"):
        usage = json.loads(path.read_text("utf-8")).get("usage") or {}
        total += (
            int(usage.get("input_tokens", 0) or 0) * input_price
            + int(usage.get("output_tokens", 0) or 0) * output_price
        ) / 1_000_000
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=0.15,
        help="누적 계산 비용이 이 값을 넘으면 남은 사례를 실행하지 않는다",
    )
    parser.add_argument("--dry-run", action="store_true", help="호출 없이 계획만 출력한다")
    parser.add_argument("--only", nargs="*", help="지정한 사례만 실행한다")
    args = parser.parse_args()

    names = case_names(args.requests)
    if args.only:
        available = set(names)
        unknown = [name for name in args.only if name not in available]
        if unknown:
            parser.error(f"없는 사례: {', '.join(unknown)}")
        # 호출 순서를 명시한 그대로 보존한다. 결함 사례를 먼저 실행한 뒤 대조군을
        # 돌리면 초반 실패 시 불필요한 후속 비용을 줄일 수 있다.
        names = list(dict.fromkeys(args.only))

    if args.dry_run:
        print(f"사례 {len(names)}건 · 모델 {MODEL} · 프롬프트 {PROMPT_VERSION}")
        print(f"예상 비용 상한 약 ${estimate_usd(len(names)):.4f} (보정 재시도 20% 가정)")
        for name in names:
            request = PlanningRequest.model_validate_json(
                (args.requests / f"{name}.json").read_text("utf-8")
            )
            schema = response_schema(
                allowed_operation_types(request.instruction), request.document
            )
            node = schema["properties"]["operations"]
            closed = node.get("maxItems") == 0
            print(f"  {name:36} {'작업 닫힘' if closed else '작업 열림'}")
        print("\n모델을 호출하지 않았습니다.")
        return

    spent = 0.0
    summary = []
    for name in names:
        if spent >= args.max_cost_usd:
            print(f"[중단] 누적 ${spent:.4f} 가 상한 ${args.max_cost_usd:.4f} 에 도달했습니다")
            break
        folder = args.output / name
        try:
            run(args.requests / f"{name}.json", folder)
            result = json.loads((folder / "result.json").read_text("utf-8"))
            spent += float(result["estimated_cost_usd"])
            summary.append(
                {
                    "case": name,
                    "status": "ok",
                    "decision": result["proposal"]["decision"],
                    "operations": [op["op"] for op in result["proposal"]["operations"]],
                    "model_calls": result["model_calls"],
                }
            )
        except Exception as exc:  # 한 건이 실패해도 나머지를 계속 본다
            case_cost = failed_case_cost(folder)
            spent += case_cost
            summary.append(
                {
                    "case": name,
                    "status": "error",
                    "error": str(exc)[:200],
                    "estimated_cost_usd": case_cost,
                }
            )
            print(f"[실패] {name}: {type(exc).__name__}: {exc}")

    (args.output / "run_summary.json").write_text(
        json.dumps(
            {
                "model": MODEL,
                "prompt_version": PROMPT_VERSION,
                "spent_usd": spent,
                "cases": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    ok = sum(item["status"] == "ok" for item in summary)
    print(f"\n실행 {len(summary)}건 · 유효 응답 {ok}건 · 계산 비용 ${spent:.5f}")


if __name__ == "__main__":
    main()
