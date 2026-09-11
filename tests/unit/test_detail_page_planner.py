import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ad_service.api.main import create_app
from ad_service.api.schemas.detail_page_plan import (
    DetailPagePlanningRequest,
    ProductApprovalRequest,
)
from ad_service.models.detail_page_planner import (
    plan_detail_page,
    response_schema,
)
from ad_service.pipelines.product_approval import approve_product_analysis


def analysis_result():
    return {
        "request_id": "analysis_1",
        "status": "needs_review",
        "persisted": False,
        "source_assets": [
            {
                "asset_id": "front",
                "role": "product_image",
                "width": 1000,
                "height": 1000,
            }
        ],
        "candidates": [
            {
                "candidate_id": "c1",
                "field": "name",
                "value": "테스트 세럼",
                "kind": "ocr_text",
                "evidence": [
                    {
                        "asset_id": "front",
                        "bbox": [10, 10, 200, 80],
                        "text": "테스트 세럼",
                    }
                ],
                "based_on_candidate_ids": [],
                "reason": None,
                "requires_confirmation": True,
            },
            {
                "candidate_id": "c2",
                "field": "brand",
                "value": "테스트 브랜드",
                "kind": "ocr_text",
                "evidence": [
                    {
                        "asset_id": "front",
                        "bbox": [10, 100, 200, 160],
                        "text": "테스트 브랜드",
                    }
                ],
                "based_on_candidate_ids": [],
                "reason": None,
                "requires_confirmation": True,
            },
            {
                "candidate_id": "c3",
                "field": "target_audience",
                "value": "성인 화장품 구매자",
                "kind": "suggestion",
                "evidence": [],
                "based_on_candidate_ids": ["c1"],
                "reason": "상품 유형 기반 추천",
                "requires_confirmation": True,
            },
        ],
        "unresolved": [
            {
                "field": "ingredients",
                "state": "unknown",
                "reason": "성분표가 보이지 않습니다.",
            }
        ],
        "conflicts": [],
        "warnings": [],
        "metrics": {
            "model": "gpt-5.4-mini",
            "model_calls": 1,
            "image_generation_calls": 0,
            "latency_ms": 100,
            "input_tokens": 100,
            "output_tokens": 50,
            "estimated_cost_usd": 0.001,
            "response_id": "resp_analysis",
        },
    }


@pytest.fixture
def approved_product():
    approval = ProductApprovalRequest.model_validate(
        {
            "product_id": "serum_1",
            "analysis": analysis_result(),
            "name": "테스트 세럼",
            "name_source_candidate_ids": ["c1"],
            "category_path": ["화장품", "세럼"],
            "confirmed_facts": [
                {
                    "fact_id": "f_brand",
                    "field": "brand",
                    "label": "브랜드",
                    "value": "테스트 브랜드",
                    "source_candidate_ids": ["c2"],
                }
            ],
            "primary_image_asset_id": "front",
        }
    )
    return approve_product_analysis(approval)


def test_approval_promotes_only_explicit_confirmations(approved_product):
    assert approved_product.name == "테스트 세럼"
    assert [item.fact_id for item in approved_product.facts] == ["f_brand"]
    assert approved_product.facts[0].source.reference.endswith(":c2")
    assert approved_product.images[0].role == "primary_product"
    assert approved_product.missing_fields == ["ingredients", "target_audience"]


def test_approval_rejects_mismatched_candidate_field():
    value = {
        "product_id": "serum_1",
        "analysis": analysis_result(),
        "name": "테스트 세럼",
        "confirmed_facts": [
            {
                "fact_id": "f_brand",
                "field": "brand",
                "label": "브랜드",
                "value": "테스트 브랜드",
                "source_candidate_ids": ["c3"],
            }
        ],
    }
    with pytest.raises(ValueError, match="field"):
        ProductApprovalRequest.model_validate(value)


@pytest.fixture
def planning_request(approved_product):
    return DetailPagePlanningRequest(
        request_id="detail_plan_1",
        product=approved_product,
        options={
            "section_limit": 5,
            "page_length": "long",
            "sales_channel": "스마트스토어",
        },
    )


def valid_model_output():
    return {
        "strategy_summary": "확정된 브랜드 정보와 상품 사진을 중심으로 간결하게 구성합니다.",
        "sections": [
            {
                "section_id": "sec_hero",
                "kind": "hero",
                "purpose": "첫 화면에서 상품을 식별합니다.",
                "layout": "image_text",
                "content_brief": "확정된 상품명과 브랜드를 중심으로 소개합니다.",
                "fact_refs": ["f_brand"],
                "source_asset_ids": ["front"],
                "image_treatment": "reuse_product_asset",
                "image_brief": "원본 상품 사진을 변형 없이 크게 배치합니다.",
            },
            {
                "section_id": "sec_features",
                "kind": "features",
                "purpose": "확인된 상품 정보를 설명합니다.",
                "layout": "feature_grid",
                "content_brief": "확인된 브랜드 정보만 사용합니다.",
                "fact_refs": ["f_brand"],
                "source_asset_ids": [],
                "image_treatment": "none",
                "image_brief": None,
            },
        ],
        "questions": [
            {
                "field": "ingredients",
                "question": "표시할 성분 정보를 입력해 주세요.",
                "reason": "성분 정보가 확인되지 않았습니다.",
            }
        ],
        "omissions": [
            {"kind": "ingredients", "reason": "확인된 성분 정보가 없어 생략합니다."}
        ],
        "warnings": ["확정된 정보가 적어 일부 섹션을 생략했습니다."],
    }


def fake_client(output):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="resp_plan",
            status="completed",
            output_text=json.dumps(output, ensure_ascii=False),
            output=[],
            usage=SimpleNamespace(input_tokens=100, output_tokens=80),
            model_dump=lambda **_: {"status": "completed", "output": output},
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create)), calls


def test_planner_returns_grounded_plan_and_real_stage_events(planning_request):
    client, calls = fake_client(valid_model_output())
    emitted = []
    before = planning_request.model_dump()
    result = plan_detail_page(planning_request, client, on_event=emitted.append)

    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-5.4-mini"
    assert calls[0]["store"] is False and calls[0]["max_output_tokens"] == 3600
    assert result.metrics.model_calls == 1
    assert result.metrics.image_analysis_calls == 0
    assert result.metrics.image_generation_calls == 0
    assert result.metrics.estimated_cost_usd == pytest.approx(0.000435)
    assert [item.sequence for item in emitted] == [1, 2, 3, 4, 5]
    assert all(item.progress_percent is None for item in emitted)
    assert result.sections[1].fact_refs == ["f_brand"]
    assert planning_request.model_dump() == before


@pytest.mark.parametrize(
    "mutate,error",
    [
        (lambda value: value["sections"][0].update(kind="features"), "첫 섹션"),
        (lambda value: value["sections"][1].update(fact_refs=["missing"]), "존재하지 않는"),
        (lambda value: value["questions"][0].update(field="price"), "missing_fields"),
        (
            lambda value: value["questions"][0].update(
                question="판매자가 पुष्टि한 성분이 있나요?"
            ),
            "외국 문자권",
        ),
    ],
)
def test_invalid_model_plan_fails_closed(planning_request, mutate, error):
    output = valid_model_output()
    mutate(output)
    client, calls = fake_client(output)
    with pytest.raises(ValueError, match=error):
        plan_detail_page(planning_request, client)
    assert len(calls) == 1


def test_preflight_budget_rejects_before_model_call(planning_request):
    planning_request.execution.budget_cap_usd = 0.000001
    client, calls = fake_client(valid_model_output())
    with pytest.raises(ValueError, match="예산"):
        plan_detail_page(planning_request, client)
    assert calls == []


def test_strict_response_schema_has_no_unsupported_keywords():
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


def test_detail_page_plan_http_endpoint(planning_request, monkeypatch):
    client, _ = fake_client(valid_model_output())
    expected = plan_detail_page(planning_request, client)
    monkeypatch.setattr(
        "ad_service.api.routes.detail_page_plan.plan_detail_page", lambda _: expected
    )
    response = TestClient(create_app()).post(
        "/v1/detail-pages/plan", json=planning_request.model_dump(mode="json")
    )
    assert response.status_code == 200
    assert response.json()["sections"][0]["kind"] == "hero"
    assert response.json()["metrics"]["image_generation_calls"] == 0
