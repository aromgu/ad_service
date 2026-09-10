"""광고 생성 API 의 요청/응답 스키마.

`docs/api_spec.md` v0.2 를 그대로 옮긴 것이다. 스키마를 바꾸면 명세서도 같이 고친다.
설계 뼈대는 `cjpark-model-baseline` 브랜치의 GenerationRequest/GenerationResult 를 따랐고,
웹 서비스에 맞춰 이미지 입력을 업로드로, 결과 이미지를 URL 로 바꿨다.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------------------
# Enum
# --------------------------------------------------------------------------------------
class OutputType(str, Enum):
    COPY = "copy"
    BANNER = "banner"
    DETAIL_VISUAL = "detail_visual"
    PRODUCT_IMAGE = "product_image"


class InputMode(str, Enum):
    TEXT_ONLY = "text_only"
    IMAGE_ONLY = "image_only"
    TEXT_AND_IMAGE = "text_and_image"


class BusinessType(str, Enum):
    FOOD_RETAIL = "food_retail"


class ProductCategory(str, Enum):
    SNACK_BEVERAGE = "snack_beverage"
    PACKAGED_FOOD = "packaged_food"
    SIDE_DISH_MEAL = "side_dish_meal"


class SalesChannel(str, Enum):
    SMART_STORE = "smart_store"
    SOCIAL_MEDIA = "social_media"
    DELIVERY_APP = "delivery_app"
    OFFLINE_STORE = "offline_store"


class CampaignGoal(str, Enum):
    PRODUCT_LAUNCH = "product_launch"
    PROMOTION = "promotion"
    BRAND_AWARENESS = "brand_awareness"
    PURCHASE_CONVERSION = "purchase_conversion"


class CopyStyle(str, Enum):
    EMOTIONAL = "emotional"
    INFORMATIVE = "informative"
    CONVERSION = "conversion"
    FRIENDLY = "friendly"
    PREMIUM = "premium"
    CUSTOM = "custom"


class CopyLength(str, Enum):
    SHORT = "short"
    STANDARD = "standard"
    DETAILED = "detailed"


class JobState(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# API 명세서 D5: MVP 는 문구와 배너만 실제 생성한다. 나머지는 422 로 거절.
SUPPORTED_OUTPUTS: frozenset[OutputType] = frozenset({OutputType.COPY, OutputType.BANNER})


# --------------------------------------------------------------------------------------
# 요청
# --------------------------------------------------------------------------------------
class GenerationOptions(StrictModel):
    """광고의 방향을 세밀하게 지정하는 선택 입력. 전부 기본값이 있다."""

    store_name: str | None = Field(default=None, max_length=80)
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
    def _clean_phrases(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            phrase = item.strip()
            if not phrase or phrase in cleaned:
                continue
            if len(phrase) > 60:
                raise ValueError("각 필수·제외 표현은 60자 이하여야 합니다")
            cleaned.append(phrase)
        return cleaned

    @model_validator(mode="after")
    def _check_conflicts(self) -> GenerationOptions:
        overlap = set(self.must_include) & set(self.avoid_phrases)
        if overlap:
            raise ValueError(f"같은 표현을 필수와 제외에 함께 넣을 수 없습니다: {sorted(overlap)}")
        if self.copy_style is CopyStyle.CUSTOM and not self.custom_instruction:
            raise ValueError("copy_style 이 custom 이면 custom_instruction 이 필요합니다")
        return self


class GenerationRequest(StrictModel):
    """``POST /api/v1/generate`` 의 JSON 본문 (multipart 인 경우 ``payload`` 파트).

    입력 이미지는 이 스키마에 담지 않는다. multipart 의 ``image`` 파트로 따로 온다.
    "text 나 image 중 하나는 필수" 규칙은 라우터에서 이미지 유무와 함께 검사한다.
    """

    request_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    text: str | None = Field(default=None, max_length=2000)
    outputs: list[OutputType] = Field(min_length=1, max_length=4)
    options: GenerationOptions = Field(default_factory=GenerationOptions)
    source: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _blank_text_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def _validate_outputs(self) -> GenerationRequest:
        if len(self.outputs) != len(set(self.outputs)):
            raise ValueError("outputs 에 중복 값을 넣을 수 없습니다")
        unsupported = [o.value for o in self.outputs if o not in SUPPORTED_OUTPUTS]
        if unsupported:
            raise ValueError(
                f"현재 MVP 는 {sorted(o.value for o in SUPPORTED_OUTPUTS)} 만 지원합니다. "
                f"지원하지 않는 outputs: {unsupported}"
            )
        return self


# --------------------------------------------------------------------------------------
# 응답
# --------------------------------------------------------------------------------------
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
    type: OutputType
    url: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    model: str
    seed: int | None = None
    text_safe_area: SafeArea | None = None
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)


class RunMetrics(StrictModel):
    latency_ms: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    copy_model: str | None = None
    image_model: str | None = None


class GenerationResult(StrictModel):
    mode: InputMode
    # 응답 키는 "copy". BaseModel.copy() 와 겹치지 않도록 속성명은 copy_result 를 쓴다.
    copy_result: CopyResult | None = Field(default=None, alias="copy")
    assets: list[GeneratedAsset] = Field(default_factory=list)
    metrics: RunMetrics
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# job 엔벨로프
# --------------------------------------------------------------------------------------
class AcceptedResponse(StrictModel):
    request_id: str
    status: JobState = JobState.PENDING
    poll_url: str


class ErrorBody(StrictModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class ErrorEnvelope(StrictModel):
    error: ErrorBody


class JobStatusResponse(StrictModel):
    request_id: str
    status: JobState
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    result: GenerationResult | None = None
    error: ErrorBody | None = None
