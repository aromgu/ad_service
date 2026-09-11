"""기존 실제 사진 분석 결과를 수정 계약으로 변환하는 오프라인 예제. 모델 호출 0회."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from ad_service.api.schemas.revision import EditableDocument, RevisionPreviewRequest
from ad_service.pipelines.revision import document_hash, preview_revision


def text_block(block_id, role, text):
    return {"content": {"type": "text", "block_id": block_id, "role": role, "text": text}}


def adapt(source: Path) -> EditableDocument:
    data = json.loads((source / "result.json").read_text("utf-8"))
    plan = data["plan"]
    if data["source_image"] not in ("input.jpg", "input.png", "input.webp"):
        raise ValueError("허용되지 않은 이미지 경로")
    with Image.open(source / data["source_image"]) as image:
        width, height = image.size
    features = []
    for i, feature in enumerate(plan["features"], 1):
        features.extend(
            [
                text_block(f"feature_{i}_heading", "heading", feature["title"]),
                text_block(f"feature_{i}_body", "feature", feature["body"]),
            ]
        )
    return EditableDocument.model_validate(
        {
            "document_id": f"photo_{data['category']}",
            "revision": 1,
            "assets": [
                {
                    "asset_id": "original_photo",
                    "role": "primary_product",
                    "width": width,
                    "height": height,
                }
            ],
            "facts": [],  # 이미지 관찰/기존 AI 문구를 판매자 확인 사실로 승격하지 않는다.
            "missing_fields": plan["missing_fields"],
            "review_notes": ["사진 분석 기반 미확인 초안입니다.", *plan["cautions"]],
            "sections": [
                {
                    "section_id": "hero",
                    "kind": "hero",
                    "blocks": [
                        text_block("product_title", "heading", plan["product_title"]),
                        text_block("hero_heading", "heading", plan["hero_title"]),
                        text_block("hero_body", "body", plan["hero_body"]),
                        {
                            "content": {
                                "type": "image",
                                "block_id": "hero_image",
                                "source_asset_id": "original_photo",
                                "alt": plan["product_title"],
                            }
                        },
                    ],
                },
                {
                    "section_id": "story",
                    "kind": "story",
                    "blocks": [
                        text_block("story_heading", "heading", plan["story_title"]),
                        text_block("story_body", "body", plan["story_body"]),
                    ],
                },
                {"section_id": "features", "kind": "features", "blocks": features},
                {
                    "section_id": "cta",
                    "kind": "cta",
                    "blocks": [
                        text_block("cta_text", "cta", plan["cta"]),
                    ],
                },
            ],
        }
    )


def export(source: Path, output: Path):
    document = adapt(source)
    output.mkdir(parents=True, exist_ok=False)

    def save(name, data):
        with (output / name).open("x", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    save("document.json", document.model_dump(mode="json"))
    cases = {
        "text": (
            "첫 제목을 짧게",
            [
                {
                    "op": "replace_text",
                    "block_id": "hero_heading",
                    "text": "브라운 코디"
                    if document.document_id.endswith("outfit")
                    else "레드 패키지",
                },
            ],
        ),
        "design": (
            "제목색 변경, 사진 크기 조정, 이미지 오른쪽 배치",
            [
                {"op": "set_style", "block_id": "hero_heading", "color": "#663333"},
                {"op": "set_style", "block_id": "hero_image", "width_percent": 80},
                {"op": "set_layout", "section_id": "hero", "layout": "image_right"},
            ],
        ),
        "structure": (
            "특징을 앞에 놓고 스토리 섹션 삭제",
            [
                {"op": "move_section", "section_id": "features", "index": 1},
                {"op": "remove_section", "section_id": "story"},
            ],
        ),
        "image_edit": (
            "상품은 유지하고 배경만 밝게",
            [
                {
                    "op": "edit_image",
                    "block_id": "hero_image",
                    "instruction": "상품은 유지하고 배경만 밝게",
                },
            ],
        ),
        "clarify": ("이 부분 좀 바꿔줘", []),
    }
    for name, (instruction, operations) in cases.items():
        request = RevisionPreviewRequest.model_validate(
            {
                "document": document.model_dump(),
                "proposal": {
                    "request_id": f"example_{name}",
                    "base_revision": document.revision,
                    "base_sha256": document_hash(document),
                    "instruction": instruction,
                    "decision": "ready" if operations else "needs_clarification",
                    "question": None if operations else "어느 부분을 어떻게 바꿀까요?",
                    "operations": operations,
                },
            }
        )
        save(f"{name}.request.json", request.model_dump(mode="json"))
        result = preview_revision(request.document, request.proposal)
        save(f"{name}.response.json", result.model_dump(mode="json"))
    save(
        "manifest.json",
        {
            "mode": "offline_contract_examples",
            "model_calls": 0,
            "note": "수정안은 코드에 적힌 예시입니다. 자연어를 AI가 해석한 결과가 아닙니다.",
            "source_result_sha256": hashlib.sha256(
                (source / "result.json").read_bytes()
            ).hexdigest(),
            "source_document_sha256": document_hash(document),
            "source": str(source.resolve()),
        },
    )
    print("수정 구조 예제 저장:", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.source, args.output)
