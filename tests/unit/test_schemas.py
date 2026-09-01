from pathlib import Path

import pytest
from pydantic import ValidationError

from ad_service.api.schemas.generation import BoundingBox, GenerationRequest


def valid_request() -> GenerationRequest:
    return GenerationRequest(
        request_id="snack_001",
        product_name="테스트 과자",
        category="식품/과자",
        features=["바삭한 식감", "고소한 맛"],
        target_audience="간식을 찾는 소비자",
        tone="밝고 친근함",
        product_image_path="data/sample.jpg",
        product_bbox=BoundingBox(xmin=10, ymin=20, xmax=300, ymax=400),
    )


def test_request_resolves_relative_image_path() -> None:
    request = valid_request()
    assert request.resolved_image_path(Path("/project")) == Path("/project/data/sample.jpg")


def test_request_rejects_invalid_id() -> None:
    payload = valid_request().model_dump()
    payload["request_id"] = "한글 공백"
    with pytest.raises(ValidationError):
        GenerationRequest.model_validate(payload)


def test_bbox_rejects_reversed_coordinates() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(xmin=20, ymin=20, xmax=10, ymax=100)
