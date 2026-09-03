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
    """이미지 파일로 만들어지는 산출물 종류입니다."""

    BANNER = "banner"
    DETAIL_VISUAL = "detail_visual"
    PRODUCT_IMAGE = "product_image"


class OutputType(str, Enum):
    """사용자가 한 번의 요청에서 선택할 수 있는 모든 결과 종류입니다."""

    COPY = "copy"
    BANNER = "banner"
    DETAIL_VISUAL = "detail_visual"
    PRODUCT_IMAGE = "product_image"


class InputMode(str, Enum):
    """어떤 입력이 들어왔는지 파이프라인이 쉽게 구분하기 위한 값입니다."""

    TEXT_ONLY = "text_only"
    IMAGE_ONLY = "image_only"
    TEXT_AND_IMAGE = "text_and_image"


class BusinessType(str, Enum):
    """현재 MVP가 우선 지원하는 소상공인 업종입니다."""

    FOOD_RETAIL = "food_retail"


class ProductCategory(str, Enum):
    """식료품 소매업 안에서 선택할 수 있는 상품 카테고리입니다."""

    SNACK_BEVERAGE = "snack_beverage"
    PACKAGED_FOOD = "packaged_food"
    SIDE_DISH_MEAL = "side_dish_meal"


class SalesChannel(str, Enum):
    """광고가 실제로 사용될 판매 채널입니다."""

    SMART_STORE = "smart_store"
    SOCIAL_MEDIA = "social_media"
    DELIVERY_APP = "delivery_app"
    OFFLINE_STORE = "offline_store"


class CampaignGoal(str, Enum):
    """이번 광고를 만드는 가장 중요한 목적입니다."""

    PRODUCT_LAUNCH = "product_launch"
    PROMOTION = "promotion"
    BRAND_AWARENESS = "brand_awareness"
    PURCHASE_CONVERSION = "purchase_conversion"


class CopyStyle(str, Enum):
    """사용자가 선택할 수 있는 광고 문구의 전개 방식입니다."""

    EMOTIONAL = "emotional"
    INFORMATIVE = "informative"
    CONVERSION = "conversion"
    FRIENDLY = "friendly"
    PREMIUM = "premium"
    CUSTOM = "custom"


class CopyLength(str, Enum):
    """광고가 노출될 공간에 맞춘 문구 길이 단계입니다."""

    SHORT = "short"
    STANDARD = "standard"
    DETAILED = "detailed"


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


class GenerationOptions(StrictModel):
    """필수 입력은 아니지만 광고의 방향을 세밀하게 지정하는 옵션입니다."""

    # MVP의 업종은 식료품 소매업으로 고정하되, 이후 다른 업종을 쉽게 추가할 수 있습니다.
    business_type: BusinessType = BusinessType.FOOD_RETAIL
    product_category: ProductCategory | None = None
    sales_channel: SalesChannel | None = None
    campaign_goal: CampaignGoal | None = None
    target_audience: str | None = Field(default=None, max_length=160)
    tone: str | None = Field(default=None, max_length=80)
    copy_style: CopyStyle = CopyStyle.INFORMATIVE
    copy_length: CopyLength = CopyLength.STANDARD
    use_emoji: bool = False
    must_include: list[str] = Field(default_factory=list, max_length=5)
    avoid_phrases: list[str] = Field(default_factory=list, max_length=10)
    custom_instruction: str | None = Field(default=None, max_length=300)
    price: str | None = Field(default=None, max_length=40)
    offer: str | None = Field(default=None, max_length=120)

    @field_validator("must_include", "avoid_phrases")
    @classmethod
    def clean_phrase_list(cls, value: list[str]) -> list[str]:
        """쉼표 입력을 변환한 뒤 생길 수 있는 빈 값과 중복을 정리합니다."""

        cleaned: list[str] = []
        for item in value:
            phrase = item.strip()
            if phrase and phrase not in cleaned:
                if len(phrase) > 60:
                    raise ValueError("각 필수·제외 표현은 60자 이하여야 합니다")
                cleaned.append(phrase)
        return cleaned

    @model_validator(mode="after")
    def validate_copy_preferences(self) -> "GenerationOptions":
        """서로 충돌하는 스타일 옵션을 모델에 전달하기 전에 막습니다."""

        overlap = set(self.must_include) & set(self.avoid_phrases)
        if overlap:
            raise ValueError(f"같은 표현을 필수와 제외에 함께 넣을 수 없습니다: {sorted(overlap)}")
        if self.copy_style is CopyStyle.CUSTOM and not self.custom_instruction:
            raise ValueError("직접 입력 스타일에는 custom_instruction이 필요합니다")
        return self


class GenerationRequest(StrictModel):
    """광고 생성의 공통 입력입니다.

    이미지가 없는 텍스트 요청과, 설명이 없는 이미지 요청을 모두 받을 수 있습니다.
    단, ``text``와 ``image_path``가 둘 다 비어 있으면 무엇을 만들지 알 수 없으므로
    검증 단계에서 요청을 거절합니다.
    """

    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    text: str | None = Field(default=None, max_length=2000)
    image_path: str | None = None
    image_bbox: BoundingBox | None = None
    outputs: list[OutputType] = Field(min_length=1, max_length=4)
    options: GenerationOptions = Field(default_factory=GenerationOptions)
    source: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def convert_legacy_request(cls, value: Any) -> Any:
        """이전에 만든 로컬 요청 JSON을 새 형식으로 자동 변환합니다.

        새 서비스에서는 ``text``와 ``image_path``를 사용합니다. 이 변환은 기존 테스트와
        저장된 예제가 한 번에 깨지지 않도록 둔 임시 호환 장치입니다.
        """

        if not isinstance(value, dict) or "product_name" not in value:
            return value

        payload = dict(value)
        product_name = str(payload.pop("product_name", "")).strip()
        category = str(payload.pop("category", "")).strip()
        raw_features = payload.pop("features", [])
        features = [str(item).strip() for item in raw_features if str(item).strip()]

        # 구조화된 과거 필드를 사람이 읽을 수 있는 하나의 설명문으로 합칩니다.
        description_parts = [product_name]
        if category:
            description_parts.append(f"카테고리: {category}")
        if features:
            description_parts.append(f"특징: {', '.join(features)}")
        payload.setdefault("text", ". ".join(description_parts))
        payload.setdefault("image_path", payload.pop("product_image_path", None))
        payload.setdefault("image_bbox", payload.pop("product_bbox", None))
        payload.setdefault(
            "outputs",
            [
                OutputType.COPY.value,
                OutputType.BANNER.value,
                OutputType.DETAIL_VISUAL.value,
                OutputType.PRODUCT_IMAGE.value,
            ],
        )
        payload.setdefault(
            "options",
            {
                "target_audience": payload.pop("target_audience", None),
                "tone": payload.pop("tone", None),
                "price": payload.pop("price", None),
                "offer": payload.pop("offer", None),
            },
        )
        return payload

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        """공백만 입력한 문자열은 입력이 없는 것과 같게 처리합니다."""

        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_inputs(self) -> "GenerationRequest":
        """입력 조합과 요청한 결과가 실제로 생성 가능한지 확인합니다."""

        if self.text is None and self.image_path is None:
            raise ValueError("text 또는 image_path 중 하나는 필요합니다")
        if OutputType.COPY in self.outputs and self.text is None:
            raise ValueError("광고 문구 생성에는 text가 필요합니다")
        if len(self.outputs) != len(set(self.outputs)):
            raise ValueError("outputs에는 중복 값을 사용할 수 없습니다")
        if self.image_bbox is not None and self.image_path is None:
            raise ValueError("image_bbox를 사용하려면 image_path가 필요합니다")
        return self

    @property
    def input_mode(self) -> InputMode:
        """라우터가 사용할 입력 모드를 계산합니다."""

        if self.text is not None and self.image_path is not None:
            return InputMode.TEXT_AND_IMAGE
        if self.image_path is not None:
            return InputMode.IMAGE_ONLY
        return InputMode.TEXT_ONLY

    def resolved_image_path(self, base_dir: Path | None = None) -> Path | None:
        """상대 이미지 경로를 실행 위치 기준의 실제 경로로 바꿉니다."""

        if self.image_path is None:
            return None
        path = Path(self.image_path)
        return path if path.is_absolute() or base_dir is None else base_dir / path

    # 아래 두 속성은 과거 로컬 유틸리티가 새 이름으로 옮겨가는 동안만 사용합니다.
    # 새 코드를 작성할 때는 각각 image_path와 image_bbox를 사용해야 합니다.
    @property
    def product_image_path(self) -> str | None:
        return self.image_path

    @property
    def product_bbox(self) -> BoundingBox | None:
        return self.image_bbox


class CopyResult(StrictModel):
    product_summary: str
    headline_candidates: list[str] = Field(min_length=3, max_length=3)
    body_candidates: list[str] = Field(min_length=3, max_length=3)
    cta_candidates: list[str] = Field(min_length=3, max_length=3)
    keywords: list[str] = Field(min_length=1, max_length=10)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("headline_candidates")
    @classmethod
    def validate_headline_lengths(cls, value: list[str]) -> list[str]:
        """카카오 네이티브 광고의 25자 한도를 넘는 제목을 거절합니다."""

        if any(len(item) > 25 for item in value):
            raise ValueError("헤드라인은 공백 포함 25자 이하여야 합니다")
        return value

    @field_validator("body_candidates")
    @classmethod
    def validate_body_lengths(cls, value: list[str]) -> list[str]:
        """검색 광고에도 재사용할 수 있도록 본문을 90자 이내로 제한합니다."""

        if any(len(item) > 90 for item in value):
            raise ValueError("본문은 공백 포함 90자 이하여야 합니다")
        return value

    @field_validator("cta_candidates")
    @classmethod
    def validate_cta_lengths(cls, value: list[str]) -> list[str]:
        """실제 광고 버튼에 바로 넣을 수 있도록 CTA를 8자 이내로 제한합니다."""

        if any(len(item) > 8 for item in value):
            raise ValueError("CTA는 공백 포함 8자 이하여야 합니다")
        return value


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
    # 일부 API 이미지 모델은 시드를 제공하지 않으므로 None도 허용합니다.
    seed: int | None = None
    text_safe_area: SafeArea | None = None
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)


class RunMetrics(StrictModel):
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    # 요청하지 않은 단계의 모델명은 비어 있을 수 있습니다.
    copy_model: str | None = None
    image_model: str | None = None
    background_remover: str | None = None
    # 전체 실행 시간과 문구 모델 자체의 생성 시간을 분리해 비교합니다.
    # Qwen의 모델 로딩 시간·VRAM, OpenAI의 응답 ID처럼 공급자마다 다른 값은
    # copy_details에 그대로 기록해 실험 보고서의 근거로 사용할 수 있습니다.
    copy_latency_ms: int | None = Field(default=None, ge=0)
    copy_input_tokens: int = Field(default=0, ge=0)
    copy_output_tokens: int = Field(default=0, ge=0)
    copy_details: dict[str, Any] = Field(default_factory=dict)


class GenerationResult(StrictModel):
    request_id: str
    mode: InputMode
    copy_result: CopyResult | None = Field(default=None, alias="copy")
    assets: list[GeneratedAsset] = Field(default_factory=list)
    metrics: RunMetrics
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


COPY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "product_summary": {"type": "string"},
        "headline_candidates": {
            "type": "array",
            "items": {"type": "string", "maxLength": 25},
            "minItems": 3,
            "maxItems": 3,
        },
        "body_candidates": {
            "type": "array",
            "items": {"type": "string", "maxLength": 90},
            "minItems": 3,
            "maxItems": 3,
        },
        "cta_candidates": {
            "type": "array",
            "items": {"type": "string", "maxLength": 8},
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
