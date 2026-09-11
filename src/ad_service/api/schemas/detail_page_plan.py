"""검수된 상품 사실을 긴 상세페이지 설계안으로 바꾸는 모델 계약."""

from typing import Literal

from pydantic import Field, model_validator

from ad_service.api.schemas.detail_page import (
    ContractModel,
    FactText,
    Identifier,
    ProductInput,
    ShortText,
)
from ad_service.api.schemas.product_analysis import FieldName, ProductAnalysisResult

SectionKind = Literal[
    "hero",
    "summary",
    "features",
    "product_details",
    "specifications",
    "usage",
    "care",
    "size_guide",
    "ingredients",
    "caution",
    "trust",
    "gallery",
    "cta",
]
LayoutHint = Literal[
    "image_text",
    "text_image",
    "text_only",
    "feature_grid",
    "spec_table",
    "gallery",
    "cta",
]
ImageTreatment = Literal[
    "none",
    "reuse_product_asset",
    "composite_product",
    "generate_supporting_visual",
]


class ConfirmedFactInput(ContractModel):
    fact_id: Identifier
    field: FieldName
    label: ShortText
    value: FactText
    source_candidate_ids: list[Identifier] = Field(default_factory=list, max_length=20)


class ProductApprovalRequest(ContractModel):
    schema_version: Literal["product-approval-0.1"] = "product-approval-0.1"
    product_id: Identifier
    revision: int = Field(default=1, ge=1, strict=True)
    analysis: ProductAnalysisResult
    name: ShortText
    name_source_candidate_ids: list[Identifier] = Field(default_factory=list, max_length=10)
    category_path: list[ShortText] = Field(default_factory=list, max_length=8)
    confirmed_facts: list[ConfirmedFactInput] = Field(default_factory=list, max_length=50)
    primary_image_asset_id: Identifier | None = None

    @model_validator(mode="after")
    def valid_confirmation(self):
        candidates = {item.candidate_id: item for item in self.analysis.candidates}
        supplied_ids = self.name_source_candidate_ids + [
            candidate_id
            for fact in self.confirmed_facts
            for candidate_id in fact.source_candidate_ids
        ]
        if not set(supplied_ids) <= set(candidates):
            raise ValueError("존재하지 않는 분석 후보를 승인 근거로 지정했습니다")
        if any(
            candidates[candidate_id].field != "name"
            for candidate_id in self.name_source_candidate_ids
        ):
            raise ValueError("상품명에는 name 후보만 근거로 지정할 수 있습니다")
        for fact in self.confirmed_facts:
            if any(
                candidates[candidate_id].field != fact.field
                for candidate_id in fact.source_candidate_ids
            ):
                raise ValueError("확정 사실의 field와 분석 후보 field가 다릅니다")
        for values, label in (
            ([item.fact_id for item in self.confirmed_facts], "fact_id"),
            ([item.field for item in self.confirmed_facts], "field"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"확정 사실의 {label}가 중복되었습니다")
        product_assets = {
            item.asset_id
            for item in self.analysis.source_assets
            if item.role == "product_image"
        }
        if (
            self.primary_image_asset_id is not None
            and self.primary_image_asset_id not in product_assets
        ):
            raise ValueError("주 이미지는 product_image 역할의 분석 자산이어야 합니다")
        return self


class DetailPagePlanningOptions(ContractModel):
    language: Literal["ko-KR"] = "ko-KR"
    sales_channel: ShortText | None = None
    target_audience: ShortText | None = None
    tone: ShortText | None = None
    page_length: Literal["compact", "standard", "long"] = "long"
    section_limit: int = Field(default=10, ge=3, le=12, strict=True)
    instruction: FactText | None = None


class DetailPagePlanningExecution(ContractModel):
    budget_cap_usd: float = Field(default=0.03, gt=0, le=1)
    max_retries: Literal[0] = 0


class DetailPagePlanningRequest(ContractModel):
    schema_version: Literal["detail-plan-0.1"] = "detail-plan-0.1"
    request_id: Identifier
    product: ProductInput
    options: DetailPagePlanningOptions = Field(default_factory=DetailPagePlanningOptions)
    execution: DetailPagePlanningExecution = Field(default_factory=DetailPagePlanningExecution)


class PlannedSection(ContractModel):
    section_id: Identifier
    kind: SectionKind
    purpose: FactText
    layout: LayoutHint
    content_brief: FactText
    fact_refs: list[Identifier] = Field(default_factory=list, max_length=50)
    source_asset_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    image_treatment: ImageTreatment
    image_brief: FactText | None = None

    @model_validator(mode="after")
    def valid_image_brief(self):
        if self.image_treatment == "none" and self.image_brief is not None:
            raise ValueError("이미지를 사용하지 않는 섹션에는 image_brief를 둘 수 없습니다")
        if self.image_treatment != "none" and self.image_brief is None:
            raise ValueError("이미지를 사용하는 섹션에는 image_brief가 필요합니다")
        return self


class PlanningQuestion(ContractModel):
    field: FieldName
    question: FactText
    reason: FactText


class PlanningOmission(ContractModel):
    kind: SectionKind
    reason: FactText


class DetailPagePlanModelOutput(ContractModel):
    strategy_summary: FactText
    sections: list[PlannedSection] = Field(min_length=1, max_length=12)
    questions: list[PlanningQuestion] = Field(default_factory=list, max_length=30)
    omissions: list[PlanningOmission] = Field(default_factory=list, max_length=20)
    warnings: list[FactText] = Field(default_factory=list, max_length=20)


PlanningStage = Literal[
    "input_validation",
    "seller_confirmation",
    "section_planning",
    "result_validation",
]


class PlanningStageEvent(ContractModel):
    sequence: int = Field(ge=1, strict=True)
    stage: PlanningStage
    status: Literal["started", "completed", "failed"]
    elapsed_ms: int = Field(ge=0, strict=True)
    progress_percent: None = None
    estimated_remaining_ms: None = None
    message: ShortText


class DetailPagePlanMetrics(ContractModel):
    model: str
    model_calls: Literal[1] = 1
    image_analysis_calls: Literal[0] = 0
    image_generation_calls: Literal[0] = 0
    latency_ms: int = Field(ge=0, strict=True)
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)
    estimated_cost_usd: float = Field(ge=0)
    preflight_cost_ceiling_usd: float = Field(ge=0)
    response_id: str


class DetailPagePlanResult(ContractModel):
    schema_version: Literal["detail-plan-0.1"] = "detail-plan-0.1"
    request_id: Identifier
    product_id: Identifier
    product_revision: int = Field(ge=1, strict=True)
    status: Literal["needs_review"] = "needs_review"
    persisted: Literal[False] = False
    strategy_summary: FactText
    sections: list[PlannedSection] = Field(min_length=1, max_length=12)
    questions: list[PlanningQuestion] = Field(default_factory=list, max_length=30)
    omissions: list[PlanningOmission] = Field(default_factory=list, max_length=20)
    warnings: list[FactText] = Field(default_factory=list, max_length=30)
    events: list[PlanningStageEvent] = Field(min_length=1)
    metrics: DetailPagePlanMetrics
