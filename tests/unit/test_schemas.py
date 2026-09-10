"""GenerationRequest / GenerationOptions 검증 규칙 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ad_service.api.schemas.generation import GenerationOptions, GenerationRequest


def test_minimal_request_ok() -> None:
    req = GenerationRequest.model_validate({"text": "국산 딸기잼 300g", "outputs": ["copy"]})
    assert req.text == "국산 딸기잼 300g"
    assert req.options.business_type.value == "food_retail"


def test_blank_text_becomes_none() -> None:
    req = GenerationRequest.model_validate({"text": "   ", "outputs": ["banner"]})
    assert req.text is None


def test_duplicate_outputs_rejected() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest.model_validate({"text": "x", "outputs": ["copy", "copy"]})


def test_unsupported_output_rejected() -> None:
    with pytest.raises(ValidationError, match="MVP"):
        GenerationRequest.model_validate({"text": "x", "outputs": ["product_image"]})


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        GenerationRequest.model_validate({"text": "x", "outputs": ["copy"], "foo": 1})


def test_custom_style_requires_instruction() -> None:
    with pytest.raises(ValidationError, match="custom_instruction"):
        GenerationOptions.model_validate({"copy_style": "custom"})


def test_must_include_avoid_overlap_rejected() -> None:
    with pytest.raises(ValidationError, match="필수와 제외"):
        GenerationOptions.model_validate(
            {"must_include": ["국산 딸기"], "avoid_phrases": ["국산 딸기"]}
        )


def test_phrases_are_deduped_and_trimmed() -> None:
    opts = GenerationOptions.model_validate({"must_include": [" 딸기 ", "딸기", "300g"]})
    assert opts.must_include == ["딸기", "300g"]
