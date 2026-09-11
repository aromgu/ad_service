import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ad_service.api.main import create_app
from ad_service.api.schemas.detail_page import ProductFact
from ad_service.models.revision_planner import (
    PlanningRequest,
    allowed_operation_types,
    plan_revision,
    reject_placeholder_values,
    response_schema,
)


@pytest.fixture
def planning_request():
    return PlanningRequest.model_validate(
        {
            "request_id": "natural_test",
            "instruction": "첫 제목만 짧게 해줘",
            "selected_block_ids": ["hero_heading"],
            "document": {
                "document_id": "cosmetics",
                "revision": 4,
                "sections": [
                    {
                        "section_id": "hero",
                        "kind": "hero",
                        "blocks": [
                            {
                                "content": {
                                    "type": "text",
                                    "block_id": "hero_heading",
                                    "role": "heading",
                                    "text": "붉은 튜브의 존재감",
                                }
                            },
                            {
                                "content": {
                                    "type": "text",
                                    "block_id": "hero_body",
                                    "role": "body",
                                    "text": "사용자가 직접 수정한 설명",
                                }
                            },
                        ],
                    },
                ],
            },
        }
    )


def client_for(decision, status="completed", refusal=False):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="test_response",
            status=status,
            usage=None,
            output_text=json.dumps(decision),
            output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])] if refusal else [],
            model_dump=lambda **_: {"status": status, "output_text": json.dumps(decision)},
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create)), calls


def ready(block_id="hero_heading"):
    return {
        "decision": "ready",
        "reply": "메인 제목을 더 짧게 다듬었어요.",
        "question": None,
        "operations": [
            {"op": "replace_text", "block_id": block_id, "text": "레드 튜브"},
        ],
    }


def test_model_contract_and_preservation(planning_request):
    before = planning_request.model_dump()
    client, calls = client_for(ready())
    raw = []
    result = plan_revision(planning_request, client, raw.append)
    assert len(calls) == 1 and len(raw) == 1
    assert calls[0]["model"] == "gpt-5.4-mini"
    assert calls[0]["store"] is False and calls[0]["max_output_tokens"] == 2400
    assert calls[0]["text"]["format"]["strict"] is True
    assert (
        result.preview.document.sections[0].blocks[1]
        == planning_request.document.sections[0].blocks[1]
    )
    assert result.preview.document.revision == 5
    assert result.model_calls == 1 and result.image_generation_calls == 0
    assert result.proposal.base_revision == 4
    assert planning_request.model_dump() == before


@pytest.mark.parametrize(
    "bad",
    [
        ready("hero_body"),
        {
            "decision": "ready",
            "reply": "섹션을 지웠어요.",
            "question": None,
            "operations": [{"op": "remove_section", "section_id": "hero"}],
        },
        {
            "decision": "ready",
            "reply": "바꿨어요.",
            "question": "둘 다?",
            "operations": ready()["operations"],
        },
        {
            "decision": "ready",
            "reply": "바꿨어요.",
            "question": None,
            "operations": [],
            "base_revision": 123,
        },
    ],
)
def test_out_of_scope_and_invalid_decision_fail_closed(planning_request, bad):
    before = planning_request.model_dump()
    client, calls = client_for(bad)
    with pytest.raises(ValueError):
        plan_revision(planning_request, client)
    # 규칙 위반은 사유를 붙여 한 번 다시 묻고, 그래도 안 되면 문서를 그대로 둔다.
    assert len(calls) == 2 and planning_request.model_dump() == before
    assert "거부되었습니다" in calls[1]["instructions"]


@pytest.mark.parametrize("status,refusal", [("incomplete", False), ("completed", True)])
def test_incomplete_refusal_recorded_without_retry(planning_request, status, refusal):
    client, calls = client_for(ready(), status, refusal)
    recorded = []
    with pytest.raises(ValueError):
        plan_revision(planning_request, client, recorded.append)
    assert len(calls) == 1 and len(recorded) == 1


def test_clarification_does_not_change_document(planning_request):
    client, _ = client_for(
        {
            "decision": "needs_clarification",
            "reply": "소재 정보가 없어 그대로 두었어요.",
            "question": "소재를 확인해 주세요",
            "operations": [],
        }
    )
    result = plan_revision(planning_request, client)
    assert result.preview.document == planning_request.document
    assert result.preview.status == "needs_clarification"


def test_strict_schema_converts_all_nested_objects():
    def check(value):
        if isinstance(value, dict):
            assert not {"oneOf", "discriminator", "default", "const"}.intersection(value)
            if value.get("type") == "object":
                assert set(value["required"]) == set(value["properties"])
                assert value["additionalProperties"] is False
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(response_schema())


def test_response_schema_limits_operations_to_instruction_intent():
    schema = response_schema({"replace_text", "set_layout"})
    variants = schema["properties"]["operations"]["items"]["anyOf"]
    operation_types = {
        schema["$defs"][variant["$ref"].rsplit("/", 1)[-1]]["properties"]["op"][
            "enum"
        ][0]
        for variant in variants
    }
    assert operation_types == {"replace_text", "set_layout"}


def test_title_instruction_cannot_replace_body(planning_request):
    planning_request.selected_block_ids = ["hero_body"]
    client, _ = client_for(ready("hero_body"))
    with pytest.raises(ValueError, match="제목 이외"):
        plan_revision(planning_request, client)


def test_explicit_fact_value_requires_fact_reference(planning_request):
    planning_request.document.facts = [
        ProductFact.model_validate(
            {
            "fact_id": "brand",
            "label": "브랜드",
            "value": "CLARINS PARIS",
            "source": {"type": "seller_input", "reference": "판매자 확인"},
            }
        )
    ]
    client, _ = client_for(
        {
            "decision": "ready",
            "reply": "제목에 사실 값을 반영했어요.",
            "question": None,
            "operations": [
                {
                    "op": "replace_text",
                    "block_id": "hero_heading",
                    "text": "CLARINS PARIS 상품",
                    "fact_refs": [],
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="fact_id"):
        plan_revision(planning_request, client)


def test_unknown_selection_before_call(planning_request):
    planning_request.selected_block_ids = ["missing"]
    client, calls = client_for(ready())
    with pytest.raises(ValueError):
        plan_revision(planning_request, client)
    assert calls == []


@pytest.mark.parametrize(
    "instruction,allowed,blocked",
    [
        ("제목만 짧게", "replace_text", "add_block"),
        ("이미지를 오른쪽에 배치하고 글자색 변경. 문구는 고치지 마", "set_layout", "replace_text"),
        ("스토리 섹션 삭제 후 특징을 맨 위로 옮겨", "remove_section", "add_section"),
        ("상품은 유지하고 배경만 밝게", "edit_image", "replace_image"),
        ("이미지 교체", "replace_image", "edit_image"),
    ],
)
def test_instruction_intent_allowlist(instruction, allowed, blocked):
    operation_types = allowed_operation_types(instruction)
    assert allowed in operation_types
    assert blocked not in operation_types


@pytest.mark.parametrize(
    "instruction,allowed",
    [
        ("이 문단 없애줘", {"remove_section", "remove_block"}),
        ("사진 좀 바꿔줘", {"replace_image"}),
        ("상품 사진 배경을 흰색으로 바꿔줘", {"edit_image"}),
        ("헤드라인을 더 강렬하게 써줘", {"replace_text"}),
        ("첫 번째 사진을 아래로 내려줘", {"move_section", "move_block"}),
        ("이 섹션을 두 칸으로 보여줘", {"set_layout"}),
        ("사진을 조금 작게 줄여줘", {"set_style"}),
    ],
)
def test_everyday_revision_phrases_are_recognized(instruction, allowed):
    assert allowed <= allowed_operation_types(instruction)


def test_background_edit_is_not_misread_as_whole_image_replacement():
    operations = allowed_operation_types("상품 사진 배경을 흰색으로 바꿔줘")
    assert "edit_image" in operations
    assert "replace_image" not in operations


def test_unsupported_bold_style_still_fails_closed():
    assert allowed_operation_types("글씨를 굵게 해줘") == set()


def test_chat_revision_http_endpoint_returns_plan_and_preview(planning_request, monkeypatch):
    model_client, _ = client_for(ready())
    expected = plan_revision(planning_request, model_client)
    monkeypatch.setattr(
        "ad_service.api.routes.revision.plan_revision", lambda _: expected
    )
    client = TestClient(create_app())

    response = client.post(
        "/v1/detail-pages/revision-plan",
        json=planning_request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["proposal"]["operations"] == [
        {
            "op": "replace_text",
            "block_id": "hero_heading",
            "text": "레드 튜브",
            "fact_refs": [],
        }
    ]
    assert result["preview"]["document"]["revision"] == 5
    assert result["model_calls"] == 1


def test_chat_revision_http_endpoint_fails_closed(planning_request, monkeypatch):
    def invalid(_):
        raise ValueError("수정 대상을 확인해 주세요")

    monkeypatch.setattr("ad_service.api.routes.revision.plan_revision", invalid)
    response = TestClient(create_app()).post(
        "/v1/detail-pages/revision-plan",
        json=planning_request.model_dump(mode="json"),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "수정 대상을 확인해 주세요"


def client_for_sequence(decisions):
    """호출할 때마다 다른 응답을 주는 가짜 클라이언트. 재시도 검증에 쓴다."""
    calls = []

    def create(**kwargs):
        decision = decisions[min(len(calls), len(decisions) - 1)]
        calls.append(kwargs)
        return SimpleNamespace(
            id="test_response",
            status="completed",
            usage=None,
            output_text=json.dumps(decision),
            output=[],
            model_dump=lambda **_: {"status": "completed"},
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create)), calls


def operation_names(schema):
    node = schema["properties"]["operations"]
    if node.get("maxItems") == 0:
        return []
    return [
        schema["$defs"][variant["$ref"].rsplit("/", 1)[-1]]["properties"]["op"]["enum"][0]
        for variant in node["items"]["anyOf"]
    ]


def test_unrecognized_instruction_closes_operations(planning_request):
    """변경 종류를 못 알아들으면 작업을 아예 만들지 못하게 닫는다.

    예전에는 빈 허용 집합이 '전체 개방'으로 뒤집혀 모호할수록 더 넓어졌다.
    """
    document = planning_request.document
    assert allowed_operation_types("이 부분 좀 바꿔줘") == set()

    schema = response_schema(allowed_operation_types("이 부분 좀 바꿔줘"), document)

    assert schema["properties"]["operations"]["maxItems"] == 0
    assert operation_names(schema) == []


def test_target_ids_are_limited_to_the_document(planning_request):
    """대상 ID를 문서에 있는 값 중 택일로 만든다. 새 ID는 지어낼 수 없다."""
    document = planning_request.document
    text_ids = [
        block.content.block_id
        for section in document.sections
        for block in section.blocks
        if block.content.type == "text"
    ]

    schema = response_schema({"replace_text"}, document)

    block_id = schema["$defs"]["ReplaceText"]["properties"]["block_id"]
    assert block_id["enum"] == text_ids
    assert "pattern" not in block_id
    assert "tmp_unused" not in block_id["enum"]


def test_operations_without_targets_are_removed(planning_request):
    """대상이 하나도 없는 작업은 스키마에서 뺀다. 시도 자체가 불가능해진다."""
    document = planning_request.document
    assert not [
        block
        for section in document.sections
        for block in section.blocks
        if block.content.type == "image"
    ]

    schema = response_schema({"edit_image", "replace_image", "set_style"}, document)

    assert operation_names(schema) == ["set_style"]


def test_placeholder_identifiers_and_text_are_rejected(planning_request):
    """스키마를 채우려고 넣은 껍데기 값을 저장 전에 끊는다."""
    filler = {
        "decision": "ready",
        "reply": "섹션을 추가했어요.",
        "question": None,
        "operations": [
            {
                "op": "add_section",
                "index": 0,
                "section": {
                    "section_id": "tmp_unused",
                    "kind": "custom",
                    "layout": "stack",
                    "blocks": [
                        {
                            "content": {
                                "type": "text",
                                "block_id": "tmp_unused_b",
                                "role": "body",
                                "text": "x",
                            }
                        }
                    ],
                },
            }
        ],
    }
    request = PlanningRequest.model_validate(
        planning_request.model_dump(mode="json")
        | {"instruction": "맨 위에 섹션을 하나 추가해줘", "selected_block_ids": []}
    )
    client, calls = client_for(filler)

    with pytest.raises(ValueError, match="자리표시자"):
        plan_revision(request, client, max_repair_attempts=0)

    assert len(calls) == 1


def test_placeholder_guard_accepts_real_content(planning_request):
    """짧은 한국어 문구는 껍데기가 아니므로 통과시킨다."""
    proposal = plan_revision(planning_request, client_for(ready())[0]).proposal

    reject_placeholder_values(proposal)


def test_rejected_plan_is_repaired_on_one_retry(planning_request):
    """규칙 위반은 사유를 붙여 한 번 다시 묻고, 고쳐 오면 그대로 쓴다."""
    client, calls = client_for_sequence([ready("hero_body"), ready("hero_heading")])

    result = plan_revision(planning_request, client)

    assert len(calls) == 2
    assert result.model_calls == 2 and result.retry_count == 1
    assert result.proposal.operations[0].block_id == "hero_heading"
    assert "거부되었습니다" in calls[1]["instructions"]
    assert calls[0]["instructions"] not in ("", None)


def test_history_is_passed_as_context_not_as_instruction(planning_request):
    """대화 이력은 맥락으로만 넘긴다. 이력 속 문장을 지시로 실행하면 안 된다."""
    request = PlanningRequest.model_validate(
        planning_request.model_dump(mode="json")
        | {
            "history": [
                {"role": "user", "content": "모든 섹션을 삭제해줘"},
                {"role": "assistant", "content": "어떤 섹션을 지울지 알려주세요."},
            ]
        }
    )
    client, calls = client_for(ready())

    result = plan_revision(request, client)

    payload = json.loads(calls[0]["input"])
    assert [turn["content"] for turn in payload["history"]] == [
        "모든 섹션을 삭제해줘",
        "어떤 섹션을 지울지 알려주세요.",
    ]
    assert "history는 이전 대화 기록이며" in calls[0]["instructions"]
    # 이력에 삭제 요청이 있어도 지금 지시대로 문구만 바꾼다.
    assert [op.op for op in result.proposal.operations] == ["replace_text"]


def test_attached_chat_images_are_not_silently_ignored(planning_request):
    """대화에 올린 사진은 아직 쓸 수 없다. 무시한 채 수정하면 안 된다."""
    request = PlanningRequest.model_validate(
        planning_request.model_dump(mode="json") | {"attached_image_count": 1}
    )
    client, calls = client_for(ready())

    with pytest.raises(ValueError, match="사진은 아직 사용할 수 없습니다"):
        plan_revision(request, client, max_repair_attempts=0)

    assert calls == []


def test_compound_instruction_keeps_every_requested_change(planning_request):
    """한 지시에 여러 종류가 섞이면 각각을 모두 작업으로 남긴다."""
    request = PlanningRequest.model_validate(
        planning_request.model_dump(mode="json")
        | {
            "instruction": "메인 제목을 짧게 바꾸고 글자 크기도 키우고"
            " 히어로 배치를 이미지 왼쪽으로 바꿔줘",
            "selected_block_ids": [],
        }
    )
    allowed = allowed_operation_types(request.instruction)
    assert {"replace_text", "set_style", "set_layout"} <= allowed

    client, _ = client_for(
        {
            "decision": "ready",
            "reply": "제목을 줄이고 크기와 배치를 함께 바꿨어요.",
            "question": None,
            "operations": [
                {"op": "replace_text", "block_id": "hero_heading", "text": "레드 튜브"},
                {"op": "set_style", "block_id": "hero_heading", "font_size": 40},
                {"op": "set_layout", "section_id": "hero", "layout": "image_left"},
            ],
        }
    )

    result = plan_revision(request, client)

    assert [op.op for op in result.proposal.operations] == [
        "replace_text",
        "set_style",
        "set_layout",
    ]
    assert result.preview.document.revision == 5


def test_reply_and_footer_reach_the_preview(planning_request):
    """답변 문장은 모델이, 변경 건수는 코드가 만든다."""
    client, _ = client_for(ready())

    result = plan_revision(planning_request, client)

    assert result.preview.reply == "메인 제목을 더 짧게 다듬었어요."
    assert result.preview.footer == "문구 1건"


def test_footer_counts_each_change_type_separately(planning_request):
    """여러 종류가 섞이면 종류별로 센다. 모델이 센 숫자를 믿지 않는다."""
    client, _ = client_for(
        {
            "decision": "ready",
            "reply": "제목과 배치를 함께 바꿨어요.",
            "question": None,
            "operations": [
                {"op": "replace_text", "block_id": "hero_heading", "text": "레드 튜브"},
                {"op": "replace_text", "block_id": "hero_body", "text": "새 본문입니다"},
                {"op": "set_layout", "section_id": "hero", "layout": "image_left"},
            ],
        }
    )
    request = PlanningRequest.model_validate(
        planning_request.model_dump(mode="json")
        | {"instruction": "제목과 본문을 바꾸고 배치도 바꿔줘", "selected_block_ids": []}
    )

    result = plan_revision(request, client)

    assert result.preview.footer == "문구 2건 · 배치 1건"


def test_clarification_still_carries_a_reply(planning_request):
    """되묻는 경우에도 화면에 보여줄 문장이 있어야 한다."""
    client, _ = client_for(
        {
            "decision": "needs_clarification",
            "reply": "어느 부분을 바꿀지 알 수 없어 그대로 두었어요.",
            "question": "어느 섹션인가요?",
            "operations": [],
        }
    )

    result = plan_revision(planning_request, client)

    assert result.preview.reply == "어느 부분을 바꿀지 알 수 없어 그대로 두었어요."
    assert result.preview.footer == "변경 없음"
    assert result.preview.document == planning_request.document


def test_unchanged_text_is_rejected_as_no_change(planning_request):
    """원문과 똑같은 문구를 돌려주면 바꾼 것이 아니므로 거부한다."""
    current = planning_request.document.sections[0].blocks[0].content.text
    client, calls = client_for(
        {
            "decision": "ready",
            "reply": "제목을 짧게 다듬었어요.",
            "question": None,
            "operations": [
                {"op": "replace_text", "block_id": "hero_heading", "text": current}
            ],
        }
    )

    with pytest.raises(ValueError, match="기존 10자보다 짧아야"):
        plan_revision(planning_request, client, max_repair_attempts=0)

    assert len(calls) == 1


def test_no_op_rejection_triggers_a_repair_retry(planning_request):
    """무변경 응답은 사유를 붙여 다시 물어 고칠 기회를 준다."""
    current = planning_request.document.sections[0].blocks[0].content.text
    unchanged = {
        "decision": "ready",
        "reply": "제목을 짧게 다듬었어요.",
        "question": None,
        "operations": [{"op": "replace_text", "block_id": "hero_heading", "text": current}],
    }
    client, calls = client_for_sequence([unchanged, ready()])

    result = plan_revision(planning_request, client)

    assert len(calls) == 2 and result.retry_count == 1
    original_length = len(current.strip())
    assert f"기존 {original_length}자보다 짧아야" in calls[1]["instructions"]
    assert f"{original_length - 1}자 이하" in calls[1]["instructions"]
    assert result.proposal.operations[0].text != current


def test_unchanged_layout_is_rejected(planning_request):
    """이미 그 배치인데 같은 값을 다시 넣는 것도 변경이 아니다."""
    current = planning_request.document.sections[0].layout
    request = PlanningRequest.model_validate(
        planning_request.model_dump(mode="json")
        | {"instruction": "히어로 배치를 바꿔줘", "selected_block_ids": []}
    )
    client, _ = client_for(
        {
            "decision": "ready",
            "reply": "배치를 바꿨어요.",
            "question": None,
            "operations": [{"op": "set_layout", "section_id": "hero", "layout": current}],
        }
    )

    with pytest.raises(ValueError, match="배치가 기존과 동일"):
        plan_revision(request, client, max_repair_attempts=0)


def test_unchanged_style_is_rejected(planning_request):
    """같은 스타일 값을 다시 넣고 수정했다고 답하지 못하게 한다."""
    request = PlanningRequest.model_validate(
        planning_request.model_dump(mode="json")
        | {"instruction": "메인 제목 글자 크기를 24로 바꿔줘"}
    )
    client, _ = client_for(
        {
            "decision": "ready",
            "reply": "글자 크기를 바꿨어요.",
            "question": None,
            "operations": [
                {"op": "set_style", "block_id": "hero_heading", "font_size": 24}
            ],
        }
    )

    with pytest.raises(ValueError, match="스타일이 기존과 동일"):
        plan_revision(request, client, max_repair_attempts=0)


def test_unchanged_section_position_is_rejected(planning_request):
    """현재 위치와 같은 인덱스로 옮기는 작업도 변경으로 세지 않는다."""
    request = PlanningRequest.model_validate(
        planning_request.model_dump(mode="json")
        | {
            "instruction": "히어로 섹션을 맨 위로 옮겨줘",
            "selected_block_ids": [],
        }
    )
    client, _ = client_for(
        {
            "decision": "ready",
            "reply": "히어로 섹션을 맨 위로 옮겼어요.",
            "question": None,
            "operations": [
                {"op": "move_section", "section_id": "hero", "index": 0}
            ],
        }
    )

    with pytest.raises(ValueError, match="섹션 위치가 기존과 동일"):
        plan_revision(request, client, max_repair_attempts=0)


def test_shorten_request_rejects_different_but_not_shorter_text(planning_request):
    """표현만 바꾸고 길이를 줄이지 않은 응답은 '짧게' 요청을 충족하지 못한다."""
    client, _ = client_for(
        {
            "decision": "ready",
            "reply": "제목을 짧게 다듬었어요.",
            "question": None,
            "operations": [
                {
                    "op": "replace_text",
                    "block_id": "hero_heading",
                    "text": "눈에 띄는 붉은색 튜브의 강한 존재감",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match=r"hero_heading 문구는 기존 \d+자보다 짧아야"):
        plan_revision(planning_request, client, max_repair_attempts=0)


def test_bigger_font_request_rejects_smaller_font(planning_request):
    """글자를 키워 달라는 요청에서 font_size를 줄이는 응답은 거부한다."""
    request = PlanningRequest.model_validate(
        planning_request.model_dump(mode="json")
        | {"instruction": "메인 제목 글자 크기를 더 크게 키워줘"}
    )
    client, _ = client_for(
        {
            "decision": "ready",
            "reply": "글자 크기를 바꿨어요.",
            "question": None,
            "operations": [
                {"op": "set_style", "block_id": "hero_heading", "font_size": 18}
            ],
        }
    )

    with pytest.raises(ValueError, match="변경 방향이 다릅니다"):
        plan_revision(request, client, max_repair_attempts=0)
