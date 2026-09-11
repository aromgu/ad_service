from fastapi import APIRouter

from ad_service.api.schemas.detail_page import DetailPageRequest, DetailPageResult
from ad_service.pipelines.detail_page import generate_mock_detail_page

router = APIRouter(prefix="/v1/mock", tags=["detail-page-mock"])


@router.post("/detail-pages", response_model=DetailPageResult)
def mock_detail_page(request: DetailPageRequest) -> DetailPageResult:
    """모델 호출·파일 저장 없이 상세페이지 JSON 구조만 확인한다."""
    return generate_mock_detail_page(request)
