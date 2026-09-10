"""``GET /api/v1/jobs/{request_id}`` — 작업 상태·결과 조회 (프론트가 2초 폴링)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ad_service.api.errors import NotFoundError
from ad_service.api.schemas.generation import JobStatusResponse

router = APIRouter(prefix="/api/v1", tags=["generation"])


@router.get("/jobs/{request_id}", response_model=JobStatusResponse)
async def get_job(request: Request, request_id: str) -> JobStatusResponse:
    job = await request.app.state.job_store.get(request_id)
    if job is None:
        raise NotFoundError(f"해당 request_id 의 작업을 찾을 수 없습니다: {request_id}")
    return JobStatusResponse(
        request_id=job.request_id,
        status=job.state,
        progress=job.progress,
        result=job.result,
        error=job.error,
    )
