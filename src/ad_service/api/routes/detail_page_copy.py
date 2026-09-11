"""상세페이지 한국어 문구 생성 API."""

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ad_service.api.schemas.detail_page_copy import (
    DetailPageCopyRequest,
    DetailPageCopyResult,
)
from ad_service.models.detail_page_copywriter import write_detail_page_copy

router = APIRouter(prefix="/v1/detail-pages", tags=["detail-page-copy"])


@router.post("/copy", response_model=DetailPageCopyResult)
async def detail_page_copy(request: DetailPageCopyRequest) -> DetailPageCopyResult:
    """승인된 섹션 계획을 편집 가능한 한국어 블록 문서로 변환한다."""
    try:
        return await run_in_threadpool(write_detail_page_copy, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail="상세페이지 문구 모델을 호출하지 못했습니다.",
        ) from exc
