"""사용자 승인 후 상세페이지 문서를 버전으로 저장하는 계약."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from ad_service.api.schemas.detail_page import ContractModel, Identifier
from ad_service.api.schemas.revision import (
    EditableDocument,
    RevisionProposal,
    SafeSameOriginAssetUrl,
)

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class RegisterDetailPageRequest(ContractModel):
    operation_id: Identifier
    document: EditableDocument
    asset_urls: dict[Identifier, SafeSameOriginAssetUrl] = Field(max_length=50)


class ApproveRevisionRequest(ContractModel):
    operation_id: Identifier
    proposal: RevisionProposal
    approved_document_sha256: Sha256
    approved_html_sha256: Sha256


class StoredRevisionResult(ContractModel):
    status: Literal["saved"] = "saved"
    document_id: Identifier
    revision: int = Field(ge=1, strict=True)
    document_sha256: Sha256
    html_sha256: Sha256
    operation_id: Identifier
    saved_at: datetime
    replayed: bool = False
    persisted: Literal[True] = True
    model_calls: Literal[0] = 0
    image_generation_calls: Literal[0] = 0
    document_url: str
    html_url: str


class StoredDocumentResult(ContractModel):
    status: Literal["stored"] = "stored"
    document: EditableDocument
    document_sha256: Sha256
    html_sha256: Sha256
    asset_urls: dict[Identifier, SafeSameOriginAssetUrl] = Field(max_length=50)
    saved_at: datetime
    document_url: str
    html_url: str
    persisted: Literal[True] = True


class RevisionHistoryItem(ContractModel):
    document_id: Identifier
    revision: int = Field(ge=1, strict=True)
    document_sha256: Sha256
    html_sha256: Sha256
    operation_id: Identifier
    saved_at: datetime
    base_revision: int | None = Field(default=None, ge=1, strict=True)


class RevisionHistoryResult(ContractModel):
    document_id: Identifier
    current_revision: int = Field(ge=1, strict=True)
    items: list[RevisionHistoryItem] = Field(min_length=1)

    @model_validator(mode="after")
    def current_revision_exists(self):
        if not any(item.revision == self.current_revision for item in self.items):
            raise ValueError("현재 버전이 이력에 없습니다")
        return self
