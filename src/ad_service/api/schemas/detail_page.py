"""UI와 독립적인 상세페이지 mock 계약. 기존 광고 생성 스키마는 유지한다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,80}$")]
BlockIdentifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,100}$")]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
FactText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
SectionType = Literal["hero", "features", "specifications", "cta"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class FactSource(ContractModel):
    type: Literal["seller_input", "catalog_import"]
    reference: ShortText


class ProductFact(ContractModel):
    fact_id: Identifier
    label: ShortText
    value: FactText
    source: FactSource


class ProductImage(ContractModel):
    asset_id: Identifier
    role: Literal["primary_product", "additional_product"]
    width: int = Field(gt=0, le=20000, strict=True)
    height: int = Field(gt=0, le=20000, strict=True)
    bbox: tuple[StrictInt, StrictInt, StrictInt, StrictInt] | None = None

    @model_validator(mode="after")
    def valid_box(self):
        if self.bbox is not None:
            xmin, ymin, xmax, ymax = self.bbox
            if not (0 <= xmin < xmax <= self.width and 0 <= ymin < ymax <= self.height):
                raise ValueError("bbox는 원본 이미지 크기 안의 [xmin, ymin, xmax, ymax]여야 합니다")
        return self


class ProductInput(ContractModel):
    product_id: Identifier
    revision: int = Field(ge=1, strict=True)
    name: ShortText
    category_path: list[ShortText] = Field(default_factory=list, max_length=8)
    facts: list[ProductFact] = Field(default_factory=list, max_length=50)
    images: list[ProductImage] = Field(default_factory=list, max_length=20)
    missing_fields: list[ShortText] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_references(self):
        for values, label in (
            ([fact.fact_id for fact in self.facts], "fact_id"),
            ([image.asset_id for image in self.images], "asset_id"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label}가 중복되었습니다")
        if len([image for image in self.images if image.role == "primary_product"]) > 1:
            raise ValueError("primary_product 이미지는 하나만 지정하세요")
        known = {fact.label for fact in self.facts}
        if known.intersection(self.missing_fields):
            raise ValueError("확인된 사실과 missing_fields에 같은 항목이 있습니다")
        return self


class DetailContentRequest(ContractModel):
    output_type: Literal["detail_page"] = "detail_page"
    language: Literal["ko-KR"] = "ko-KR"
    sales_channel: ShortText | None = None
    target_audience: ShortText | None = None
    tone: ShortText | None = None
    instruction: FactText | None = None
    section_plan: list[SectionType] = Field(
        default_factory=lambda: ["hero", "features", "specifications"],
        min_length=1,
        max_length=4,
    )
    image_strategy: Literal["composite", "direct_edit"] = "composite"
    primary_image_asset_id: Identifier | None = None

    @model_validator(mode="after")
    def unique_sections(self):
        if len(self.section_plan) != len(set(self.section_plan)):
            raise ValueError("section_plan에 중복된 섹션 종류가 있습니다")
        return self


class MockExecutionOptions(ContractModel):
    budget_cap_usd: float = Field(default=0, ge=0)


class DetailPageRequest(ContractModel):
    schema_version: Literal["mock-0.1"]
    request_id: Identifier
    product: ProductInput
    content_request: DetailContentRequest = Field(default_factory=DetailContentRequest)
    execution: MockExecutionOptions = Field(default_factory=MockExecutionOptions)

    @model_validator(mode="after")
    def valid_primary_image(self):
        primary = self.content_request.primary_image_asset_id
        images = {image.asset_id for image in self.product.images}
        if images and primary is None:
            raise ValueError("사진이 있으면 primary_image_asset_id를 지정하세요")
        if primary is not None and primary not in images:
            raise ValueError("primary_image_asset_id가 product.images에 없습니다")
        if self.content_request.image_strategy == "direct_edit" and primary is None:
            raise ValueError("direct_edit에는 원본 상품 사진이 필요합니다")
        return self


class TextBlock(ContractModel):
    block_id: BlockIdentifier
    type: Literal["text"] = "text"
    role: Literal["heading", "body", "feature", "cta"]
    text: FactText
    fact_refs: list[Identifier] = Field(default_factory=list)


class ImageBlock(ContractModel):
    block_id: BlockIdentifier
    type: Literal["image"] = "image"
    source_asset_id: Identifier
    alt: ShortText
    render_status: Literal["reference_only"] = "reference_only"


class SpecificationRow(ContractModel):
    label: ShortText
    value: FactText
    fact_refs: list[Identifier] = Field(min_length=1)


class TableBlock(ContractModel):
    block_id: BlockIdentifier
    type: Literal["table"] = "table"
    rows: list[SpecificationRow] = Field(min_length=1, max_length=50)


ContentBlock = Annotated[TextBlock | ImageBlock | TableBlock, Field(discriminator="type")]


class DetailSection(ContractModel):
    section_id: Identifier
    type: SectionType
    visible: bool = True
    layout: Literal["image_text", "text_only", "feature_list", "spec_table", "cta"]
    blocks: list[ContentBlock] = Field(min_length=1)


class OmittedSection(ContractModel):
    type: SectionType
    reason: str


class ContentReview(ContractModel):
    requires_human_approval: Literal[True] = True
    missing_fields: list[str]
    omitted_sections: list[OmittedSection]
    warnings: list[str]


class MockMetrics(ContractModel):
    mode: Literal["mock"] = "mock"
    model_calls: Literal[0] = 0
    estimated_cost_usd: Literal[0.0] = 0.0
    providers: list[str] = Field(default_factory=list, max_length=0)


class DetailPageResult(ContractModel):
    schema_version: Literal["mock-0.1"] = "mock-0.1"
    request_id: Identifier
    product_id: Identifier
    product_revision: int
    output_type: Literal["detail_page"] = "detail_page"
    status: Literal["needs_review"] = "needs_review"
    persisted: Literal[False] = False
    resolved_language: Literal["ko-KR"] = "ko-KR"
    sections: list[DetailSection]
    assets: list[ProductImage]
    review: ContentReview
    execution: MockMetrics = Field(default_factory=MockMetrics)
