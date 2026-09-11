"""등록된 상품 관리 — 스마트스토어에 올라가 있는 상품을 커머스 API 에서 바로 읽는다."""

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.models import ProductDraft
from app.naver import catalog
from app.naver import service as naver_service
from app.naver.client import NaverApiError
from app.schemas.common import ProductDraftOut, StoreProductPage

router = APIRouter(prefix="/store-products", tags=["store-products"])


def _http_error(e: NaverApiError) -> HTTPException:
    """키가 없는 등 설정 문제는 503, 스토어에 없는 상품은 404, 네이버가 거절한 건 502."""
    if e.status == 404:
        code = status.HTTP_404_NOT_FOUND
    elif e.status is None:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_502_BAD_GATEWAY
    return HTTPException(code, str(e))


@router.get("", response_model=StoreProductPage)
def list_store_products(
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """스마트스토어 상품 목록. 로컬 DB 가 아니라 네이버에 있는 그대로를 보여 준다."""
    try:
        return naver_service.list_store_products(page=page, size=size)
    except NaverApiError as e:
        raise _http_error(e) from e


@router.post("/{origin_product_no}/open", response_model=ProductDraftOut)
def open_store_product(
    user: CurrentUser,
    db: DbSession,
    origin_product_no: str = Path(pattern=r"^\d{1,20}$"),
) -> ProductDraft:
    """목록에서 고른 상품을 검토 화면에서 열 수 있게 한다.

    이 앱으로 등록한 상품이면 그 초안을, 판매자센터 등에서 올린 상품이면 새 초안을 쓴다.
    어느 쪽이든 네이버의 현재 값으로 맞춘 뒤 돌려준다.
    """
    try:
        client = naver_service.get_client()
        detail = naver_service.fetch_origin(client, origin_product_no)
        leaf_id = str(detail["originProduct"].get("leafCategoryId") or "")
        category_path = catalog.path_of(client, leaf_id) if leaf_id else ""
    except NaverApiError as e:
        raise _http_error(e) from e

    draft = (
        db.query(ProductDraft)
        .filter(
            ProductDraft.user_id == user.id,
            ProductDraft.naver_origin_product_no == origin_product_no,
        )
        .order_by(ProductDraft.updated_at.desc())
        .first()
    )
    if draft is None:
        draft = ProductDraft(user_id=user.id)
        db.add(draft)
    naver_service.sync_from_naver(
        draft, detail, origin_product_no=origin_product_no, category_path=category_path
    )
    db.commit()
    db.refresh(draft)
    return draft
