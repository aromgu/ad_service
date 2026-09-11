import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ad_service.api.main import create_app
from ad_service.api.schemas.detail_page_copy import DetailPageCopyRequest
from ad_service.models.detail_page_copywriter import response_schema, write_detail_page_copy


def request_value():
    return {
        "request_id": "copy_1",
        "document_id": "document_1",
        "plan_approved": True,
        "product": {
            "product_id": "serum_1",
            "revision": 1,
            "name": "Super Restorative Concentrate",
            "category_path": ["화장품"],
            "facts": [
                {
                    "fact_id": "f_brand",
                    "label": "브랜드",
                    "value": "CLARINS PARIS",
                    "source": {"type": "seller_input", "reference": "confirmed:c1"},
                },
                {
                    "fact_id": "f_type",
                    "label": "상품 유형",
                    "value": "목·데콜테용 컨센트레이트",
                    "source": {"type": "seller_input", "reference": "confirmed:c2"},
                },
            ],
            "images": [
                {
                    "asset_id": "front",
                    "role": "primary_product",
                    "width": 1000,
                    "height": 1000,
                    "bbox": None,
                }
            ],
            "missing_fields": ["volume"],
        },
        "plan": {
            "request_id": "plan_1",
            "product_id": "serum_1",
            "product_revision": 1,
            "strategy_summary": "확인된 정보만 사용합니다.",
            "sections": [
                {
                    "section_id": "hero_01",
                    "kind": "hero",
                    "purpose": "상품 소개",
                    "layout": "image_text",
                    "content_brief": "상품명과 브랜드를 소개합니다.",
                    "fact_refs": ["f_brand", "f_type"],
                    "source_asset_ids": ["front"],
                    "image_treatment": "reuse_product_asset",
                    "image_brief": "원본 사진을 사용합니다.",
                },
                {
                    "section_id": "specs_01",
                    "kind": "specifications",
                    "purpose": "상품 정보",
                    "layout": "spec_table",
                    "content_brief": "확인된 정보를 표로 정리합니다.",
                    "fact_refs": ["f_brand", "f_type"],
                    "source_asset_ids": [],
                    "image_treatment": "none",
                    "image_brief": None,
                },
                {
                    "section_id": "cta_01",
                    "kind": "cta",
                    "purpose": "행동 유도",
                    "layout": "cta",
                    "content_brief": "과장 없이 정보를 확인하도록 안내합니다.",
                    "fact_refs": [],
                    "source_asset_ids": [],
                    "image_treatment": "none",
                    "image_brief": None,
                },
            ],
            "questions": [],
            "omissions": [],
            "warnings": [],
            "events": [
                {
                    "sequence": 1,
                    "stage": "result_validation",
                    "status": "completed",
                    "elapsed_ms": 10,
                    "progress_percent": None,
                    "estimated_remaining_ms": None,
                    "message": "검증했습니다.",
                }
            ],
            "metrics": {
                "model": "gpt-5.4-mini",
                "latency_ms": 10,
                "input_tokens": 10,
                "output_tokens": 10,
                "estimated_cost_usd": 0.001,
                "preflight_cost_ceiling_usd": 0.02,
                "response_id": "resp_plan",
            },
        },
        "options": {
            "tone": "프리미엄하고 차분한",
            "must_include": ["CLARINS PARIS"],
            "prohibited_phrases": ["최고"],
        },
    }


@pytest.fixture
def copy_request():
    return DetailPageCopyRequest.model_validate(request_value())


def valid_output():
    return {
        "sections": [
            {
                "section_id": "hero_01",
                "text_blocks": [
                    {
                        "block_id": "hero_heading",
                        "role": "heading",
                        "text": "CLARINS PARIS, 목·데콜테 케어",
                        "fact_refs": ["f_brand", "f_type"],
                    },
                    {
                        "block_id": "hero_body",
                        "role": "body",
                        "text": "목·데콜테용 컨센트레이트 상품입니다.",
                        "fact_refs": ["f_type"],
                    },
                ],
                "table_blocks": [],
            },
            {
                "section_id": "specs_01",
                "text_blocks": [
                    {
                        "block_id": "specs_heading",
                        "role": "heading",
                        "text": "확인된 상품 정보",
                        "fact_refs": [],
                    }
                ],
                "table_blocks": [
                    {
                        "block_id": "specs_table",
                        "rows": [
                            {
                                "label": "브랜드",
                                "value": "CLARINS PARIS",
                                "fact_refs": ["f_brand"],
                            },
                            {
                                "label": "상품 유형",
                                "value": "목·데콜테용 컨센트레이트",
                                "fact_refs": ["f_type"],
                            },
                        ],
                    }
                ],
            },
            {
                "section_id": "cta_01",
                "text_blocks": [
                    {
                        "block_id": "cta_text",
                        "role": "cta",
                        "text": "상품 정보 확인하기",
                        "fact_refs": [],
                    }
                ],
                "table_blocks": [],
            },
        ],
        "warnings": [],
    }


def fake_client(output):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="resp_copy",
            status="completed",
            output_text=json.dumps(output, ensure_ascii=False),
            output=[],
            usage=SimpleNamespace(input_tokens=200, output_tokens=100),
            model_dump=lambda **_: {"status": "completed", "output": output},
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create)), calls


def test_copywriter_builds_editable_document(copy_request):
    client, calls = fake_client(valid_output())
    emitted = []
    before = copy_request.model_dump()
    result = write_detail_page_copy(copy_request, client, on_event=emitted.append)

    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-5.4-mini"
    assert calls[0]["store"] is False and calls[0]["max_output_tokens"] == 4000
    assert result.metrics.image_analysis_calls == 0
    assert result.metrics.image_generation_calls == 0
    assert result.metrics.estimated_cost_usd == pytest.approx(0.0006)
    assert [event.sequence for event in emitted] == [1, 2, 3, 4, 5, 6]
    assert all(event.progress_percent is None for event in emitted)
    assert result.document.sections[0].layout == "image_left"
    assert result.document.sections[0].blocks[-1].content.type == "image"
    assert result.document.sections[1].blocks[-1].content.type == "table"
    assert copy_request.model_dump() == before


def test_image_only_body_can_use_source_asset_as_grounding(copy_request):
    copy_request.plan.sections[0].fact_refs = []
    copy_request.options.must_include = []
    output = valid_output()
    output["sections"][0]["text_blocks"] = [
        {
            "block_id": "hero_heading",
            "role": "heading",
            "text": "상품 이미지 안내",
            "fact_refs": [],
        },
        {
            "block_id": "hero_body",
            "role": "body",
            "text": "정면 사진을 확인해 주세요.",
            "fact_refs": [],
        },
    ]
    client, _ = fake_client(output)
    result = write_detail_page_copy(copy_request, client)
    image_section = next(
        section
        for section in result.document.sections
        if section.section_id == "hero_01"
    )
    assert image_section.blocks[-1].content.type == "image"


def test_copy_document_drops_plan_stage_only_warning(copy_request):
    copy_request.plan.warnings = [
        "이 결과는 섹션 설계안이며 카피·이미지·HTML을 생성하거나 저장하지 않았습니다.",
        "패키지 표기 원문은 효능으로 단정하지 마세요.",
    ]
    client, _ = fake_client(valid_output())
    result = write_detail_page_copy(copy_request, client)
    assert result.document.review_notes == [
        "패키지 표기 원문은 효능으로 단정하지 마세요."
    ]


def test_ungrounded_body_without_fact_or_image_fails(copy_request):
    output = valid_output()
    output["sections"][2]["text_blocks"].append(
        {
            "block_id": "cta_body",
            "role": "body",
            "text": "추가 안내 문구입니다.",
            "fact_refs": [],
        }
    )
    client, _ = fake_client(output)
    with pytest.raises(ValueError, match="상품 사실 또는 이미지 근거"):
        write_detail_page_copy(copy_request, client)


@pytest.mark.parametrize(
    "mutate,error",
    [
        (lambda value: value["sections"].reverse(), "같은 순서"),
        (
            lambda value: value["sections"][0]["text_blocks"][1].update(
                fact_refs=["missing"]
            ),
            "범위 밖",
        ),
        (
            lambda value: value["sections"][1]["table_blocks"][0]["rows"][0].update(
                value="다른 브랜드"
            ),
            "그대로",
        ),
        (
            lambda value: value["sections"][2]["text_blocks"][0].update(text="SHOP NOW"),
            "한국어",
        ),
        (
            lambda value: value["sections"][2]["text_blocks"][0].update(
                text="상품을 अभी 확인하기"
            ),
            "외국 문자권",
        ),
    ],
)
def test_invalid_copy_fails_closed(copy_request, mutate, error):
    output = valid_output()
    mutate(output)
    client, calls = fake_client(output)
    with pytest.raises(ValueError, match=error):
        write_detail_page_copy(copy_request, client)
    assert len(calls) == 1


def test_unknown_must_include_is_rejected_before_call(copy_request):
    copy_request.options.must_include = ["임의 신제품"]
    client, calls = fake_client(valid_output())
    with pytest.raises(ValueError, match="must_include"):
        write_detail_page_copy(copy_request, client)
    assert calls == []


def test_copy_request_rejects_unknown_plan_references():
    value = request_value()
    value["plan"]["sections"][0]["fact_refs"] = ["unknown_fact"]
    with pytest.raises(ValueError, match="존재하지 않는 상품 사실"):
        DetailPageCopyRequest.model_validate(value)


def test_copy_request_rejects_unknown_source_asset():
    value = request_value()
    value["plan"]["sections"][0]["source_asset_ids"] = ["unknown_asset"]
    with pytest.raises(ValueError, match="존재하지 않는 상품 이미지"):
        DetailPageCopyRequest.model_validate(value)


def test_warning_with_unexpected_script_fails_closed(copy_request):
    output = valid_output()
    output["warnings"] = ["검토 필요 अभी"]
    client, _ = fake_client(output)
    with pytest.raises(ValueError, match="외국 문자권"):
        write_detail_page_copy(copy_request, client)


def test_strict_schema_keywords():
    def check(value):
        if isinstance(value, dict):
            forbidden = {"oneOf", "discriminator", "default", "const", "prefixItems"}
            assert not forbidden.intersection(value)
            if value.get("type") == "object":
                assert set(value["required"]) == set(value["properties"])
                assert value["additionalProperties"] is False
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(response_schema())


def test_copy_http_endpoint(copy_request, monkeypatch):
    client, _ = fake_client(valid_output())
    expected = write_detail_page_copy(copy_request, client)
    monkeypatch.setattr(
        "ad_service.api.routes.detail_page_copy.write_detail_page_copy",
        lambda _: expected,
    )
    response = TestClient(create_app()).post(
        "/v1/detail-pages/copy", json=copy_request.model_dump(mode="json")
    )
    assert response.status_code == 200
    blocks = response.json()["document"]["sections"][0]["blocks"]
    assert blocks[-1]["content"]["type"] == "image"
