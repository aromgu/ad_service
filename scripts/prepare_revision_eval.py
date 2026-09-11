"""실제 계획 모델 평가용 요청을 준비한다. 기대값은 모델 입력에 포함하지 않는다."""

import argparse
import json
from pathlib import Path

from ad_service.models.revision_planner import PlanningRequest

CASES = [
    (
        "01_text",
        "outfit",
        "메인 제목만 지금보다 짧게 바꿔줘. 다른 내용은 그대로 둬.",
        ["hero_heading"],
        "ready",
        ["replace_text"],
    ),
    (
        "02_layout",
        "cosmetics",
        "맨 위 소개 섹션에서 이미지를 오른쪽에 배치하고, "
        "메인 제목 글자색만 #990000으로 바꿔줘. 문구는 고치지 마.",
        [],
        "ready",
        ["set_layout", "set_style"],
    ),
    ("03_ambiguous", "outfit", "이 부분 좀 바꿔줘.", [], "needs_clarification", []),
    (
        "04_missing_fact",
        "cosmetics",
        "이 화장품은 주름 개선 효과가 있다고 강조해줘.",
        [],
        "needs_clarification",
        [],
    ),
    (
        "05_image_intent",
        "cosmetics",
        "맨 위 상품 사진에서 상품의 포장과 글자는 유지하고 "
        "주변 배경만 밝은 흰색 스튜디오로 바꿔줘.",
        ["hero_image"],
        "ready",
        ["edit_image"],
    ),
    (
        "06_structure",
        "outfit",
        "스토리 섹션만 삭제하고 상품 특징 섹션을 맨 위로 옮겨줘. 나머지 내용은 고치지 마.",
        [],
        "ready",
        ["remove_section", "move_section"],
    ),
]


def prepare(source: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    expectations = []
    for case, category, instruction, selection, decision, ops in CASES:
        document = json.loads((source / category / "document.json").read_text("utf-8"))
        request = PlanningRequest.model_validate(
            {
                "request_id": case,
                "document": document,
                "instruction": instruction,
                "selected_block_ids": selection,
            }
        )
        with (output / f"{case}.json").open("x", encoding="utf-8") as file:
            json.dump(request.model_dump(mode="json"), file, ensure_ascii=False, indent=2)
        expectations.append({"case": case, "decision": decision, "operation_types": ops})
    with (output / "expectations.json").open("x", encoding="utf-8") as file:
        json.dump(expectations, file, ensure_ascii=False, indent=2)
    print("평가 요청 준비:", len(expectations), output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.output)
