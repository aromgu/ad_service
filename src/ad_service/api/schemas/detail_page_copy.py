"""승인된 상세페이지 계획을 편집 가능한 한국어 문서로 만드는 계약."""

from typing import Literal

from pydantic import Field, model_validator

from ad_service.api.schemas.detail_page import (
    BlockIdentifier,
    ContractModel,
    FactText,
    Identifier,
    ProductInput,
    ShortText,
)
from ad_service.api.schemas.detail_page_plan import DetailPagePlanResult
from ad_service.api.schemas.revision import EditableDocument


class DetailPageCopyOptions(ContractModel):
    language: Literal["ko-KR"] = "ko-KR"
    tone: FactText = "프리미엄하고 차분한"
    headline_max_chars: int = Field(default=48, ge=10, le=80, strict=True)
    body_max_chars: int = Field(default=360, ge=80, le=800, strict=True)
    feature_max_chars: int = Field(default=160, ge=30, le=300, strict=True)
    cta_max_chars: int = Field(default=24, ge=4, le=40, strict=True)
    must_include: list[FactText] = Field(default_factory=list, max_length=20)
    prohibited_phrases: list[FactText] = Field(default_factory=list, max_length=30)


class DetailPageCopyExecution(ContractModel):
    budget_cap_usd: float = Field(default=0.03, gt=0, le=1)
    max_retries: Literal[0] = 0


class DetailPageCopyRequest(ContractModel):
    schema_version: Literal["detail-copy-0.1"] = "detail-copy-0.1"
    request_id: Identifier
    document_id: Identifier
    product: ProductInput
    plan: DetailPagePlanResult
    plan_approved: Literal[True]
    options: DetailPageCopyOptions = Field(default_factory=DetailPageCopyOptions)
    execution: DetailPageCopyExecution = Field(default_factory=DetailPageCopyExecution)

    @model_validator(mode="after")
    def matching_plan(self):
        if (self.plan.product_id, self.plan.product_revision) != (
            self.product.product_id,
            self.product.revision,
        ):
            raise ValueError("승인된 계획과 상품 버전이 일치하지 않습니다")
        fact_ids = {fact.fact_id for fact in self.product.facts}
        asset_ids = {image.asset_id for image in self.product.images}
        section_ids = [section.section_id for section in self.plan.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("승인된 계획의 section_id가 중복되었습니다")
        if any(not set(section.fact_refs) <= fact_ids for section in self.plan.sections):
            raise ValueError("승인된 계획이 존재하지 않는 상품 사실을 참조합니다")
        if any(
            not set(section.source_asset_ids) <= asset_ids
            for section in self.plan.sections
        ):
            raise ValueError("승인된 계획이 존재하지 않는 상품 이미지를 참조합니다")
        return self


class GeneratedTextBlock(ContractModel):
    block_id: BlockIdentifier
    role: Literal["heading", "body", "feature", "cta"]
    text: FactText
    fact_refs: list[Identifier] = Field(default_factory=list, max_length=50)


class GeneratedTableRow(ContractModel):
    label: ShortText
    value: FactText
    fact_refs: list[Identifier] = Field(min_length=1, max_length=10)


class GeneratedTableBlock(ContractModel):
    block_id: BlockIdentifier
    rows: list[GeneratedTableRow] = Field(min_length=1, max_length=50)


class GeneratedSectionCopy(ContractModel):
    section_id: Identifier
    text_blocks: list[GeneratedTextBlock] = Field(default_factory=list, max_length=20)
    table_blocks: list[GeneratedTableBlock] = Field(default_factory=list, max_length=5)


class DetailPageCopyModelOutput(ContractModel):
    sections: list[GeneratedSectionCopy] = Field(min_length=1, max_length=12)
    warnings: list[FactText] = Field(default_factory=list, max_length=20)


CopyStage = Literal[
    "input_validation",
    "copy_generation",
    "document_assembly",
    "result_validation",
]


class CopyStageEvent(ContractModel):
    sequence: int = Field(ge=1, strict=True)
    stage: CopyStage
    status: Literal["started", "completed", "failed"]
    elapsed_ms: int = Field(ge=0, strict=True)
    progress_percent: None = None
    estimated_remaining_ms: None = None
    message: FactText


class DetailPageCopyMetrics(ContractModel):
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


class DetailPageCopyResult(ContractModel):
    schema_version: Literal["detail-copy-0.1"] = "detail-copy-0.1"
    request_id: Identifier
    status: Literal["needs_review"] = "needs_review"
    persisted: Literal[False] = False
    document: EditableDocument
    events: list[CopyStageEvent] = Field(min_length=1)
    warnings: list[FactText]
    metrics: DetailPageCopyMetrics
