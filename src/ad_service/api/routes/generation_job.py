"""생성 중 화면에서 조회할 비동기 작업 상태 API."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from ad_service.api.routes.generate import get_pipeline
from ad_service.api.schemas.generation import GenerationResult
from ad_service.api.schemas.generation_job import (
    CreateGenerationJobRequest,
    GenerationJobEventsResult,
    GenerationJobResult,
    RetryGenerationJobRequest,
)
from ad_service.core.config import get_settings
from ad_service.pipelines.generation_job import (
    GenerationJobConflict,
    GenerationJobCorrupt,
    GenerationJobError,
    GenerationJobNotFound,
    GenerationJobService,
)

router = APIRouter(prefix="/v1/generation-jobs", tags=["generation-jobs"])


@lru_cache
def get_generation_job_service() -> GenerationJobService:
    return GenerationJobService(
        get_settings().output_root,
        pipeline_factory=get_pipeline,
    )


def _http_error(exc: GenerationJobError) -> HTTPException:
    if isinstance(exc, GenerationJobNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, GenerationJobConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, GenerationJobCorrupt):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.post("", response_model=GenerationJobResult, status_code=202)
def create_generation_job(request: CreateGenerationJobRequest) -> GenerationJobResult:
    try:
        return get_generation_job_service().create(request)
    except GenerationJobError as exc:
        raise _http_error(exc) from exc


@router.get("/{job_id}", response_model=GenerationJobResult)
def generation_job(job_id: str) -> GenerationJobResult:
    try:
        return get_generation_job_service().load(job_id)
    except GenerationJobError as exc:
        raise _http_error(exc) from exc


@router.get("/{job_id}/events", response_model=GenerationJobEventsResult)
def generation_job_events(
    job_id: str,
    after_sequence: int = Query(default=0, ge=0),
) -> GenerationJobEventsResult:
    try:
        return get_generation_job_service().events(job_id, after_sequence)
    except GenerationJobError as exc:
        raise _http_error(exc) from exc


@router.post("/{job_id}/cancel", response_model=GenerationJobResult)
def cancel_generation_job(job_id: str) -> GenerationJobResult:
    try:
        return get_generation_job_service().cancel(job_id)
    except GenerationJobError as exc:
        raise _http_error(exc) from exc


@router.post("/{job_id}/retry", response_model=GenerationJobResult, status_code=202)
def retry_generation_job(
    job_id: str,
    request: RetryGenerationJobRequest,
) -> GenerationJobResult:
    try:
        return get_generation_job_service().retry(job_id, request)
    except GenerationJobError as exc:
        raise _http_error(exc) from exc


@router.get("/{job_id}/result", response_model=GenerationResult)
def generation_job_result(job_id: str) -> GenerationResult:
    try:
        return get_generation_job_service().result(job_id)
    except GenerationJobError as exc:
        raise _http_error(exc) from exc
