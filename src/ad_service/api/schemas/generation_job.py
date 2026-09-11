"""비동기 생성 작업의 상태·이벤트·취소·재시도 계약."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from ad_service.api.schemas.generation import GenerationRequest, StrictModel
from ad_service.core.progress import PipelineStage


class GenerationJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CreateGenerationJobRequest(StrictModel):
    request: GenerationRequest
    seed: int = Field(default=0, ge=0, le=2**31 - 1, strict=True)


class RetryGenerationJobRequest(StrictModel):
    new_request_id: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )


class GenerationJobError(StrictModel):
    code: str
    message: str
    retryable: bool


class GenerationJobEvent(StrictModel):
    sequence: int = Field(ge=1, strict=True)
    status: GenerationJobStatus
    stage: PipelineStage
    message: str
    created_at: datetime
    progress_percent: None = None
    estimated_remaining_ms: None = None
    asset_type: str | None = None
    completed_assets: int | None = Field(default=None, ge=0, strict=True)
    total_assets: int | None = Field(default=None, ge=0, strict=True)


class GenerationJobResult(StrictModel):
    schema_version: Literal["generation-job-0.1"] = "generation-job-0.1"
    job_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    request_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    retry_of: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    attempt: int = Field(ge=1, strict=True)
    status: GenerationJobStatus
    stage: PipelineStage
    sequence: int = Field(ge=1, strict=True)
    message: str
    progress_percent: None = None
    estimated_remaining_ms: None = None
    completed_assets: int = Field(default=0, ge=0, strict=True)
    total_assets: int = Field(default=0, ge=0, strict=True)
    model_calls: int = Field(default=0, ge=0, strict=True)
    image_generation_calls: int = Field(default=0, ge=0, strict=True)
    preprocessing_calls: int = Field(default=0, ge=0, strict=True)
    recorded_cost_usd: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    created_at: datetime
    started_at: datetime | None = None
    updated_at: datetime
    cancel_requested_at: datetime | None = None
    finished_at: datetime | None = None
    result_url: str | None = None
    error: GenerationJobError | None = None
    can_cancel: bool
    can_retry: bool
    replayed: bool = False
    persisted: Literal[True] = True


class GenerationJobEventsResult(StrictModel):
    job_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    latest_sequence: int = Field(ge=1, strict=True)
    items: list[GenerationJobEvent]
