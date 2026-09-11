"""상품 승인과 상세페이지 섹션 계획 API."""

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ad_service.api.schemas.detail_page import ProductInput
from ad_service.api.schemas.detail_page_plan import (
    DetailPagePlanningRequest,
    DetailPagePlanResult,
    ProductApprovalRequest,
)
from ad_service.models.detail_page_planner import plan_detail_page
from ad_service.pipelines.product_approval import approve_product_analysis

router = APIRouter(prefix="/v1", tags=["detail-page-planning"])


@router.post("/product-analysis/approve", response_model=ProductInput)
def approve_analysis(request: ProductApprovalRequest) -> ProductInput:
    """사용자가 확인한 값만 상세페이지·블로그·등록봇 공통 상품 정보로 변환한다."""
    try:
        return approve_product_analysis(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/detail-pages/plan", response_model=DetailPagePlanResult)
async def detail_page_plan(request: DetailPagePlanningRequest) -> DetailPagePlanResult:
    """확정 상품 사실로 긴 상세페이지 섹션 설계안을 생성한다."""
    try:
        return await run_in_threadpool(plan_detail_page, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail="상세페이지 설계 모델을 호출하지 못했습니다.",
        ) from exc
