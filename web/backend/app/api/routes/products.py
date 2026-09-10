from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.korean import eul_reul
from app.db.models import ProductDraft
from app.naver import catalog as naver_catalog
from app.naver.client import NaverApiError
from app.naver.service import get_client
from app.naver.service import register as naver_register
from app.schemas.common import CategoryCandidate, ProductDraftOut, ProductDraftPatch

router = APIRouter(prefix="/product-drafts", tags=["products"])


def _get_owned(db, draft_id: str, user_id: str) -> ProductDraft:
    draft = db.get(ProductDraft, draft_id)
    if draft is None or draft.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록 정보를 찾을 수 없습니다.")
    return draft


@router.get("/categories/search", response_model=list[CategoryCandidate])
def search_categories(q: str = Query(min_length=1, max_length=60)) -> list[CategoryCandidate]:
    """네이버 실제 카테고리 검색.

    등록에는 말단 카테고리 ID(leafCategoryId)가 반드시 필요해서 경로와 함께 내려준다.
    """
    try:
        client = get_client()
    except NaverApiError as e:
        # 키 미설정을 빈 결과로 숨기면 원인을 못 찾는다.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    hits = naver_catalog.search(client, q.strip())
    return [CategoryCandidate(id=h["id"], path=h["path"]) for h in hits]


@router.get("/{draft_id}", response_model=ProductDraftOut)
def get_draft(draft_id: str, user: CurrentUser, db: DbSession) -> ProductDraft:
    return _get_owned(db, draft_id, user.id)


@router.patch("/{draft_id}", response_model=ProductDraftOut)
def patch_draft(
    draft_id: str, payload: ProductDraftPatch, user: CurrentUser, db: DbSession
) -> ProductDraft:
    """4c 검토 화면의 수정 저장. 등록 완료 후에도 '등록 내용 수정'으로 다시 들어올 수 있다."""
    draft = _get_owned(db, draft_id, user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field in ("options", "kc"):
            value = (
                [o if isinstance(o, dict) else o.model_dump() for o in value]
                if field == "options"
                else value
            )
        setattr(draft, field, value)
    db.commit()
    db.refresh(draft)
    return draft


@router.post("/{draft_id}/register", response_model=ProductDraftOut)
def register(draft_id: str, user: CurrentUser, db: DbSession) -> ProductDraft:
    """네이버 스마트스토어에 상품을 실제로 등록한다.

    이미지는 네이버 이미지 API 로 다시 올린다(외부 URL 직접 입력은 거부된다).
    상품정보제공고시 항목은 상품군 정의를 조회해 채운다.
    """
    draft = _get_owned(db, draft_id, user.id)

    missing: list[str] = []
    if not draft.product_name.strip():
        missing.append("상품명")
    if not draft.selected_category.strip() or not draft.selected_category_id.strip():
        missing.append("카테고리")
    if draft.price is None or draft.price <= 0:
        missing.append("판매가")
    if missing:
        # 마지막 항목에만 조사를 붙인다. "상품명, 판매가를 먼저 입력해 주세요."
        listed = ", ".join(missing[:-1] + [eul_reul(missing[-1])])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{listed} 먼저 입력해 주세요.")

    try:
        result = naver_register(draft)
    except NaverApiError as e:
        # 네이버가 알려준 이유를 그대로 보여준다 — 사용자가 직접 고칠 수 있는 정보다.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    draft.naver_origin_product_no = str(result.get("originProductNo") or "")
    draft.naver_channel_product_no = str(result.get("smartstoreChannelProductNo") or "")
    draft.status = "registered"
    draft.registered_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(draft)
    return draft
