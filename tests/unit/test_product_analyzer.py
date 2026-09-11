import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from ad_service.api.schemas.product_analysis import ProductAnalysisRequest
from ad_service.models.product_analyzer import (
    ImagePayload,
    analyze_product,
    response_schema,
)


def png_payload(size=(40, 30), color="red"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return ImagePayload(output.getvalue(), "image/png")


@pytest.fixture
def analysis_request():
    return ProductAnalysisRequest.model_validate(
        {
            "request_id": "analysis_test",
            "purpose": "product_autofill",
            "assets": [
                {
                    "asset_id": "front",
                    "role": "product_image",
                    "width": 40,
                    "height": 30,
                }
            ],
            "seller_input": {"name": None, "facts": []},
            "requested_fields": ["name", "material"],
        }
    )


def fake_client(result, *, status="completed", refusal=False):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            id="analysis_response",
            status=status,
            output_text=json.dumps(result, ensure_ascii=False),
            output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])]
            if refusal
            else [],
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
            model_dump=lambda **_: {"status": status, "output_text": result},
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create)), calls


def valid_output():
    return {
        "candidates": [
            {
                "candidate_id": "c1",
                "field": "name",
                "value": "붉은 튜브 상품",
                "kind": "visual_observation",
                "evidence": [
                    {"asset_id": "front", "bbox": [2, 2, 35, 28], "text": None}
                ],
                "based_on_candidate_ids": [],
                "reason": None,
                "requires_confirmation": True,
            }
        ],
        "unresolved": [
            {
                "field": "material",
                "state": "unknown",
                "reason": "사진만으로 재질을 확인할 수 없습니다.",
            }
        ],
        "conflicts": [],
        "warnings": ["판매자 확인 전 후보입니다."],
    }


def test_analyzer_sends_images_once_and_returns_review_only(analysis_request):
    client, calls = fake_client(valid_output())
    before = analysis_request.model_dump()
    recorded = []
    result = analyze_product(
        analysis_request, {"front": png_payload()}, client, recorded.append
    )

    assert len(calls) == 1 and len(recorded) == 1
    call = calls[0]
    assert call["model"] == "gpt-5.4-mini"
    assert call["store"] is False and call["max_output_tokens"] == 3200
    assert call["text"]["format"]["strict"] is True
    assert any(item["type"] == "input_image" for item in call["input"][0]["content"])
    assert result.status == "needs_review" and not result.persisted
    assert result.metrics.model_calls == 1 and result.metrics.image_generation_calls == 0
    assert result.metrics.estimated_cost_usd == pytest.approx(0.000255)
    assert result.unresolved[0].field == "material"
    assert analysis_request.model_dump() == before


@pytest.mark.parametrize(
    "mutate,error",
    [
        (lambda output: output["unresolved"].clear(), "누락"),
        (
            lambda output: output["candidates"][0].update(field="price"),
            "요청하지 않은",
        ),
        (
            lambda output: output["candidates"][0]["evidence"][0].update(
                bbox=[0, 0, 400, 300]
            ),
            "bbox",
        ),
    ],
)
def test_invalid_model_outputs_fail_closed(analysis_request, mutate, error):
    output = valid_output()
    mutate(output)
    client, _ = fake_client(output)
    with pytest.raises(ValueError, match=error):
        analyze_product(analysis_request, {"front": png_payload()}, client)


def test_payload_metadata_and_ids_are_verified_before_model_call(analysis_request):
    client, calls = fake_client(valid_output())
    with pytest.raises(ValueError, match="asset_id"):
        analyze_product(analysis_request, {"other": png_payload()}, client)
    with pytest.raises(ValueError, match="크기"):
        analyze_product(analysis_request, {"front": png_payload((20, 20))}, client)
    with pytest.raises(ValueError, match="MIME"):
        analyze_product(
            analysis_request,
            {"front": ImagePayload(png_payload().data, "image/jpeg")},
            client,
        )
    assert calls == []


@pytest.mark.parametrize("status,refusal", [("incomplete", False), ("completed", True)])
def test_incomplete_or_refused_response_is_not_retried(
    analysis_request, status, refusal
):
    client, calls = fake_client(valid_output(), status=status, refusal=refusal)
    with pytest.raises(ValueError):
        analyze_product(analysis_request, {"front": png_payload()}, client)
    assert len(calls) == 1


def test_strict_response_schema_has_no_unsupported_keywords():
    def check(value):
        if isinstance(value, dict):
            assert not {
                "oneOf",
                "discriminator",
                "default",
                "const",
                "prefixItems",
            }.intersection(value)
            if value.get("type") == "object":
                assert set(value["required"]) == set(value["properties"])
                assert value["additionalProperties"] is False
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(response_schema())
