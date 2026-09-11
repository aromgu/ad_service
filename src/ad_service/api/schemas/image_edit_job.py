"""상세페이지 이미지 편집 작업의 승인·실행 계약."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ad_service.api.schemas.detail_page import (
    BlockIdentifier,
    ContractModel,
    FactText,
    Identifier,
)
from ad_service.api.schemas.detail_page_store import Sha256
from ad_service.api.schemas.revision import (
    EditableDocument,
    ImageEditIntent,
    SafeSameOriginAssetUrl,
)

ImageSize = Literal["1024x1024", "1024x1536", "1536x1024"]
ImageQuality = Literal["low", "medium", "high"]
ImageEditJobStatus = Literal[
    "pending_approval",
    "running",
    "succeeded",
    "failed",
]
PromptText = Annotated[str, StringConstraints(min_length=1, max_length=5000)]


class CreateImageEditJobRequest(ContractModel):
    """미리보기에서 나온 이미지 편집 의도를 실행 전 작업으로 등록한다."""

    job_id: Identifier
    base_revision: int = Field(ge=1, strict=True)
    base_document_sha256: Sha256
    intent: ImageEditIntent
    seed: int = Field(default=0, ge=0, le=2**31 - 1, strict=True)


class ApproveImageEditJobRequest(ContractModel):
    """표시된 실행 사양과 비용 상한을 사용자가 승인한다."""

    operation_id: Identifier
    approval_sha256: Sha256
    approved_cost_cap_usd: float = Field(ge=0, le=30, allow_inf_nan=False)


class ApproveImageEditAttachmentRequest(ContractModel):
    """검수한 편집 결과를 새 문서 자산과 버전으로 확정한다."""

    operation_id: Identifier
    approved_document_sha256: Sha256
    approved_html_sha256: Sha256
    approved_result_file_sha256: Sha256


class ImageEditAttachmentPreview(ContractModel):
    status: Literal["needs_review"] = "needs_review"
    job_id: Identifier
    document: EditableDocument
    document_sha256: Sha256
    html: str
    html_sha256: Sha256
    result_asset_id: Identifier
    result_asset_url: SafeSameOriginAssetUrl
    result_file_sha256: Sha256
    persisted: Literal[False] = False
    model_calls: Literal[0] = 0
    image_generation_calls: Literal[0] = 0
    note: str = "편집 결과를 새 자산으로 연결한 승인 전 상세페이지 미리보기입니다."


class ImageEditJobResult(ContractModel):
    schema_version: Literal["image-edit-job-0.1"] = "image-edit-job-0.1"
    job_id: Identifier
    status: ImageEditJobStatus
    document_id: Identifier
    base_revision: int = Field(ge=1, strict=True)
    base_document_sha256: Sha256
    block_id: BlockIdentifier
    source_asset_id: Identifier
    source_asset_url: SafeSameOriginAssetUrl
    source_file_sha256: Sha256
    instruction: FactText
    prompt: PromptText
    provider: Literal["mock", "gpt-image-2"]
    model: str
    quality: ImageQuality
    output_size: ImageSize
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)
    seed: int = Field(ge=0, strict=True)
    estimated_cost_usd: float = Field(ge=0, allow_inf_nan=False)
    approval_sha256: Sha256
    approval_required: bool
    approved_cost_cap_usd: float | None = Field(
        default=None,
        ge=0,
        le=30,
        allow_inf_nan=False,
    )
    approval_operation_id: Identifier | None = None
    recorded_cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    latency_ms: int | None = Field(default=None, ge=0, strict=True)
    result_asset_id: Identifier | None = None
    result_asset_url: SafeSameOriginAssetUrl | None = None
    result_file_sha256: Sha256 | None = None
    attached_revision: int | None = Field(default=None, ge=2, strict=True)
    attachment_operation_id: Identifier | None = None
    created_at: datetime
    approved_at: datetime | None = None
    finished_at: datetime | None = None
    attached_at: datetime | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    replayed: bool = False
    persisted: Literal[True] = True
    model_calls: int = Field(default=0, ge=0, le=1, strict=True)
    image_generation_calls: int = Field(default=0, ge=0, le=1, strict=True)
