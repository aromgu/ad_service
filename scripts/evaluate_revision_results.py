"""실제 수정 계획 실험 결과를 기대값과 비교하고 표준 API 단가로 사용량을 계산한다."""

import argparse
import json
from pathlib import Path

from build_revision_eval_v2 import SEMANTIC_CHECKS

from ad_service.api.schemas.revision import RevisionProposal
from ad_service.models.revision_planner import (
    ModelDecision,
    PlanningRequest,
    enforce_attachment_support,
    enforce_instruction_intent,
    enforce_requested_transformations,
    enforce_selection,
    enforce_text_grounding,
    reject_no_op_operations,
    reject_placeholder_values,
)
from ad_service.pipelines.revision import document_hash, preview_revision

INPUT_USD_PER_MILLION = 0.75
CACHED_INPUT_USD_PER_MILLION = 0.075
OUTPUT_USD_PER_MILLION = 4.50


def response_text(response):
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content["text"]
    raise ValueError("출력 텍스트가 없습니다")


def usage_cost(usage):
    total_input = usage["input_tokens"]
    cached = usage.get("input_tokens_details", {}).get("cached_tokens", 0)
    output = usage["output_tokens"]
    return (
        (total_input - cached) * INPUT_USD_PER_MILLION
        + cached * CACHED_INPUT_USD_PER_MILLION
        + output * OUTPUT_USD_PER_MILLION
    ) / 1_000_000


def unchanged_targets(request, decision) -> list[str]:
    """값이 그대로인 대상 목록. 비어 있지 않으면 실제로 바뀐 것이 없다."""
    if decision.decision != "ready":
        return []
    blocks = {
        block.content.block_id: block.content
        for section in request.document.sections
        for block in section.blocks
    }
    layouts = {section.section_id: section.layout for section in request.document.sections}
    unchanged = []
    for operation in decision.operations:
        if operation.op == "replace_text":
            target = blocks.get(operation.block_id)
            if target is not None and target.type == "text" and target.text == operation.text:
                unchanged.append(operation.block_id)
        elif operation.op == "set_layout":
            if layouts.get(operation.section_id) == operation.layout:
                unchanged.append(operation.section_id)
    return unchanged


def _contains_subset(actual, expected) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_subset(actual[key], value)
            for key, value in expected.items()
        )
    return actual == expected


def semantic_issues(request, decision, checks: dict) -> list[str]:
    """대상·값·길이처럼 작업 이름만으로 알 수 없는 품질 조건을 검사한다."""
    if decision.decision != "ready" or not checks:
        return []
    operations = [
        operation.model_dump(mode="json", exclude_none=True)
        for operation in decision.operations
    ]
    issues: list[str] = []
    unused = set(range(len(operations)))
    for expected in checks.get("operations", []):
        matched = next(
            (
                index
                for index in unused
                if _contains_subset(operations[index], expected)
            ),
            None,
        )
        if matched is None:
            issues.append(f"요구 작업 불일치: {expected}")
        else:
            unused.remove(matched)

    blocks = {
        block.content.block_id: block
        for section in request.document.sections
        for block in section.blocks
    }
    replacements = {
        operation.block_id: operation.text
        for operation in decision.operations
        if operation.op == "replace_text"
    }
    for block_id in checks.get("shorter_text_blocks", []):
        original = blocks[block_id].content.text
        changed = replacements.get(block_id)
        if changed is None or len(changed.strip()) >= len(original.strip()):
            issues.append(f"문구가 짧아지지 않음: {block_id}")

    styles = {
        operation.block_id: operation
        for operation in decision.operations
        if operation.op == "set_style"
    }
    for block_id, fields in checks.get("increased_style", {}).items():
        operation = styles.get(block_id)
        for field in fields:
            before = getattr(blocks[block_id].style, field)
            after = getattr(operation, field, None) if operation is not None else None
            if after is None or after <= before:
                issues.append(f"스타일 값이 커지지 않음: {block_id}.{field}")

    serialized = json.dumps(operations, ensure_ascii=False)
    for text in checks.get("required_new_text", []):
        if text not in serialized:
            issues.append(f"요청한 새 문구 누락: {text}")
    return issues


def runtime_model_calls(folder: Path) -> int:
    """보정 재시도를 포함한 실제 호출 수. 없으면 응답 파일 수로 센다."""
    result = folder / "result.json"
    if result.exists():
        return int(json.loads(result.read_text("utf-8")).get("model_calls", 1))
    return len(list(folder.glob("response_*.json"))) or 1


def runtime_usage(folder: Path) -> dict:
    """보정 재시도를 포함한 모든 원시 응답의 사용량을 합산한다.

    response.json은 마지막 response_N.json의 복사본이므로 숫자가 붙은 응답이
    있으면 그것만 사용해 중복 계산을 막는다.
    """
    paths = sorted(folder.glob("response_[0-9]*.json"))
    if not paths:
        paths = [folder / "response.json"]
    usages = [json.loads(path.read_text("utf-8"))["usage"] for path in paths]
    return {
        "input_tokens": sum(int(usage.get("input_tokens", 0)) for usage in usages),
        "input_tokens_details": {
            "cache_write_tokens": sum(
                int(usage.get("input_tokens_details", {}).get("cache_write_tokens", 0))
                for usage in usages
            ),
            "cached_tokens": sum(
                int(usage.get("input_tokens_details", {}).get("cached_tokens", 0))
                for usage in usages
            ),
        },
        "output_tokens": sum(int(usage.get("output_tokens", 0)) for usage in usages),
        "output_tokens_details": {
            "reasoning_tokens": sum(
                int(usage.get("output_tokens_details", {}).get("reasoning_tokens", 0))
                for usage in usages
            )
        },
        "total_tokens": sum(int(usage.get("total_tokens", 0)) for usage in usages),
    }


def evaluate(
    root: Path, output: Path | None = None, only: list[str] | None = None
):
    expected = {
        item["case"]: item
        for item in json.loads((root / "requests/expectations.json").read_text("utf-8"))
    }
    if only:
        unknown = [name for name in only if name not in expected]
        if unknown:
            raise ValueError(f"없는 사례: {', '.join(unknown)}")
        expected = {name: expected[name] for name in dict.fromkeys(only)}
    cases = []
    for name, target in expected.items():
        folder = root / name
        execution = json.loads((folder / "execution.json").read_text("utf-8"))
        response = json.loads((folder / "response.json").read_text("utf-8"))
        decision = ModelDecision.model_validate_json(response_text(response))
        actual_ops = [operation.op for operation in decision.operations]
        quality_pass = decision.decision == target["decision"] and sorted(actual_ops) == sorted(
            target["operation_types"]
        )
        # 9/10 실패는 전부 "바꾸라고 했는데 추가했다" 였다. 같은 탈출이 남았는지 따로 센다.
        escaped_to_add = sorted(
            {op for op in actual_ops if op.startswith("add_")} - set(target["operation_types"])
        )
        request = PlanningRequest.model_validate_json(
            (root / f"requests/{name}.json").read_text("utf-8")
        )
        checks = target.get("semantic_checks") or SEMANTIC_CHECKS.get(name, {})
        meaning_issues = semantic_issues(request, decision, checks)
        if meaning_issues:
            quality_pass = False
        # 작업 종류만 보면 "바꿨다고 하고 아무것도 안 바꾼" 응답을 놓친다. 값을 직접 비교한다.
        no_op_targets = unchanged_targets(request, decision)
        if no_op_targets:
            quality_pass = False
        proposal = RevisionProposal(
            request_id=request.request_id,
            base_revision=request.document.revision,
            base_sha256=document_hash(request.document),
            instruction=request.instruction,
            **decision.model_dump(),
        )
        post_fix_status = "accepted"
        try:
            enforce_selection(request, proposal)
            enforce_instruction_intent(request, proposal)
            enforce_text_grounding(request, proposal)
            enforce_attachment_support(request, proposal)
            enforce_requested_transformations(request, proposal)
            reject_no_op_operations(request, proposal)
            reject_placeholder_values(proposal)
            preview_revision(request.document, proposal)
        except ValueError as error:
            post_fix_status = "blocked"
            meaning_issues.append(f"현재 안전 검증 차단: {error}")
            quality_pass = False
        usage = runtime_usage(folder)
        cases.append(
            {
                "case": name,
                "group": target.get("group", "?"),
                "note": target.get("note", ""),
                "quality": "pass" if quality_pass else "fail",
                "escaped_to_add": escaped_to_add,
                "unchanged_targets": no_op_targets,
                "semantic_issues": meaning_issues,
                "expected_decision": target["decision"],
                "expected_operation_types": target["operation_types"],
                "actual_decision": decision.decision,
                "actual_operation_types": actual_ops,
                "runtime_result_file": (folder / "result.json").exists(),
                "runtime_failure_file": (folder / "failure.json").exists(),
                "model_calls": runtime_model_calls(folder),
                "post_fix_safety_check": post_fix_status,
                "model": execution["model"],
                "prompt_version": execution["prompt_version"],
                "response_id": response["id"],
                "usage": usage,
                "calculated_standard_cost_usd": usage_cost(usage),
            }
        )
    total_usage = {
        key: sum(case["usage"][key] for case in cases)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    total_usage["cached_input_tokens"] = sum(
        case["usage"].get("input_tokens_details", {}).get("cached_tokens", 0) for case in cases
    )
    groups: dict[str, dict] = {}
    for case in cases:
        bucket = groups.setdefault(case["group"], {"total": 0, "passes": 0})
        bucket["total"] += 1
        bucket["passes"] += case["quality"] == "pass"

    models = sorted({case["model"] for case in cases})
    prompt_versions = sorted({case["prompt_version"] for case in cases})
    result = {
        "model": models[0] if len(models) == 1 else models,
        "prompt_version": (
            prompt_versions[0] if len(prompt_versions) == 1 else prompt_versions
        ),
        "calls": len(cases),
        "model_calls_total": sum(case["model_calls"] for case in cases),
        "escaped_to_add_cases": [c["case"] for c in cases if c["escaped_to_add"]],
        "unchanged_cases": [c["case"] for c in cases if c["unchanged_targets"]],
        "by_group": groups,
        "quality_passes": sum(case["quality"] == "pass" for case in cases),
        "quality_failures": sum(case["quality"] == "fail" for case in cases),
        "image_generation_calls": 0,
        "usage": total_usage,
        "rate_usd_per_million": {
            "input": INPUT_USD_PER_MILLION,
            "cached_input": CACHED_INPUT_USD_PER_MILLION,
            "output": OUTPUT_USD_PER_MILLION,
        },
        "calculated_standard_cost_usd": sum(case["calculated_standard_cost_usd"] for case in cases),
        "cost_note": "응답 usage와 표준 단가로 계산한 값이며 실제 청구 내역이 아닙니다.",
        "cases": cases,
    }
    output = output or root / "evaluation.json"
    with output.open("x", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--only", nargs="*", help="지정한 사례만 채점한다")
    args = parser.parse_args()
    evaluate(args.root, args.output, args.only)
