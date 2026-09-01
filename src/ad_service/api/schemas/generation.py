from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


class AssetType(str, Enum):
    BANNER = "banner"
    DETAIL_VISUAL = "detail_visual"
    PRODUCT_IMAGE = "product_image"


class BoundingBox(StrictModel):
    xmin: int = Field(ge=0)
    ymin: int = Field(ge=0)
    xmax: int = Field(gt=0)
    ymax: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(self) -> "BoundingBox":
        if self.xmax <= self.xmin or self.ymax <= self.ymin:
            raise ValueError("bounding box max values must exceed min values")
        return self

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.xmin, self.ymin, self.xmax, self.ymax)


class GenerationRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    product_name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    features: list[str] = Field(min_length=1, max_length=8)
    target_audience: str = Field(min_length=1, max_length=160)
    tone: str = Field(min_length=1, max_length=80)
    price: str | None = Field(default=None, max_length=40)
    offer: str | None = Field(default=None, max_length=120)
    product_image_path: str
    product_bbox: BoundingBox | None = None
    source: dict[str, Any] = Field(default_factory=dict)

    @field_validator("features")
    @classmethod
    def clean_features(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty feature is required")
        return cleaned

    def resolved_image_path(self, base_dir: Path | None = None) -> Path:
        path = Path(self.product_image_path)
        return path if path.is_absolute() or base_dir is None else base_dir / path


class CopyResult(StrictModel):
    product_summary: str
    headline_candidates: list[str] = Field(min_length=3, max_length=3)
    body_candidates: list[str] = Field(min_length=3, max_length=3)
    cta_candidates: list[str] = Field(min_length=3, max_length=3)
    keywords: list[str] = Field(min_length=1, max_length=10)
    warnings: list[str] = Field(default_factory=list)


class SafeArea(StrictModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class GeneratedAsset(StrictModel):
    type: AssetType
    path: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    model: str
    prompt: str
    seed: int
    text_safe_area: SafeArea | None = None
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)


class RunMetrics(StrictModel):
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    copy_model: str
    image_model: str
    background_remover: str


class GenerationResult(StrictModel):
    request_id: str
    copy_result: CopyResult = Field(alias="copy")
    assets: list[GeneratedAsset]
    metrics: RunMetrics
    warnings: list[str] = Field(default_factory=list)


COPY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "product_summary": {"type": "string"},
        "headline_candidates": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
        "body_candidates": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
        "cta_candidates": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
        "keywords": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "product_summary",
        "headline_candidates",
        "body_candidates",
        "cta_candidates",
        "keywords",
        "warnings",
    ],
}
