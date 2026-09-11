"""상세페이지·블로그·상품등록이 공유하는 상품 이미지 분석 계약."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from ad_service.api.schemas.detail_page import (
    ContractModel,
    FactText,
    Identifier,
    ProductFact,
    ShortText,
)

FieldName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$",
    ),
]


class AnalysisAsset(ContractModel):
    asset_id: Identifier
    role: Literal["product_image", "existing_detail_page"]
    width: int = Field(gt=0, le=20000, strict=True)
    height: int = Field(gt=0, le=20000, strict=True)


class SellerAnalysisInput(ContractModel):
    name: ShortText | None = None
    category_hint: ShortText | None = None
    facts: list[ProductFact] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_facts(self):
        ids = [fact.fact_id for fact in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("seller_input fact_id가 중복되었습니다")
        return self


class AnalysisExecutionOptions(ContractModel):
    budget_cap_usd: float = Field(default=0.05, ge=0, le=5)
    max_retries: Literal[0] = 0


class ProductAnalysisRequest(ContractModel):
    schema_version: Literal["product-analysis-0.1"] = "product-analysis-0.1"
    request_id: Identifier
    purpose: Literal["product_autofill", "detail_page", "blog", "product_registration"]
    assets: list[AnalysisAsset] = Field(min_length=1, max_length=8)
    seller_input: SellerAnalysisInput = Field(default_factory=SellerAnalysisInput)
    requested_fields: list[FieldName] = Field(min_length=1, max_length=30)
    execution: AnalysisExecutionOptions = Field(default_factory=AnalysisExecutionOptions)

    @model_validator(mode="after")
    def unique_values(self):
        asset_ids = [asset.asset_id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("asset_id가 중복되었습니다")
        if len(self.requested_fields) != len(set(self.requested_fields)):
            raise ValueError("requested_fields가 중복되었습니다")
        return self


class AnalysisEvidence(ContractModel):
    asset_id: Identifier
    bbox: list[int] = Field(min_length=4, max_length=4)
    text: FactText | None = None


class AnalysisCandidate(ContractModel):
    candidate_id: Identifier
    field: FieldName
    value: FactText
    kind: Literal["ocr_text", "visual_observation", "suggestion"]
    evidence: list[AnalysisEvidence] = Field(default_factory=list, max_length=8)
    based_on_candidate_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    reason: FactText | None = None
    requires_confirmation: Literal[True] = True

    @model_validator(mode="after")
    def evidence_matches_kind(self):
        if self.kind in {"ocr_text", "visual_observation"} and not self.evidence:
            raise ValueError("OCR·시각 관찰 후보에는 이미지 근거가 필요합니다")
        if self.kind == "suggestion" and not self.reason:
            raise ValueError("추천 후보에는 추천 이유가 필요합니다")
        return self


class UnresolvedField(ContractModel):
    field: FieldName
    state: Literal["unknown"] = "unknown"
    reason: FactText


class AnalysisConflict(ContractModel):
    field: FieldName
    seller_value: FactText
    observed_value: FactText
    reason: FactText
    requires_confirmation: Literal[True] = True


class ProductAnalysisModelOutput(ContractModel):
    candidates: list[AnalysisCandidate] = Field(default_factory=list, max_length=90)
    unresolved: list[UnresolvedField] = Field(default_factory=list, max_length=30)
    conflicts: list[AnalysisConflict] = Field(default_factory=list, max_length=30)
    warnings: list[FactText] = Field(default_factory=list, max_length=20)


class ProductAnalysisMetrics(ContractModel):
    model: str
    model_calls: Literal[1] = 1
    image_generation_calls: Literal[0] = 0
    latency_ms: int = Field(ge=0, strict=True)
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    response_id: str


class ProductAnalysisResult(ContractModel):
    schema_version: Literal["product-analysis-0.1"] = "product-analysis-0.1"
    request_id: Identifier
    status: Literal["needs_review"] = "needs_review"
    persisted: Literal[False] = False
    source_assets: list[AnalysisAsset]
    candidates: list[AnalysisCandidate]
    unresolved: list[UnresolvedField]
    conflicts: list[AnalysisConflict]
    warnings: list[FactText]
    metrics: ProductAnalysisMetrics

    @model_validator(mode="after")
    def references_are_valid(self):
        candidate_ids = [item.candidate_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate_id가 중복되었습니다")
        known_candidates = set(candidate_ids)
        assets = {item.asset_id: item for item in self.source_assets}
        for candidate in self.candidates:
            if not set(candidate.based_on_candidate_ids) <= known_candidates:
                raise ValueError("존재하지 않는 후보를 근거로 참조했습니다")
            for evidence in candidate.evidence:
                asset = assets.get(evidence.asset_id)
                if asset is None:
                    raise ValueError("존재하지 않는 이미지 근거입니다")
                xmin, ymin, xmax, ymax = evidence.bbox
                if not (0 <= xmin < xmax <= asset.width and 0 <= ymin < ymax <= asset.height):
                    raise ValueError("근거 bbox가 원본 이미지 범위를 벗어났습니다")
        return self
