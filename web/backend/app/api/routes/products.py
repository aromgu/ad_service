from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.models import Job, ProductDraft
from app.naver import catalog as naver_catalog
from app.naver.client import NaverApiError
from app.naver.service import MissingFieldsError, WrongStateError, get_client
from app.naver.service import delete as naver_delete
from app.naver.service import register as naver_register
from app.naver.service import update as naver_update
from app.schemas.common import CategoryCandidate, ProductDraftOut, ProductDraftPatch

router = APIRouter(prefix="/product-drafts", tags=["products"])


def _get_owned(db, draft_id: str, user_id: str) -> ProductDraft:
    draft = db.get(ProductDraft, draft_id)
    if draft is None or draft.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록 정보를 찾을 수 없습니다.")
    return draft


def _http_error(e: NaverApiError) -> HTTPException:
    """빠진 입력 400, 상태가 맞지 않음 409, 스토어에 없는 상품 404, 그 밖의 네이버 실패 502."""
    if isinstance(e, MissingFieldsError):
        code = status.HTTP_400_BAD_REQUEST
    elif isinstance(e, WrongStateError):
        code = status.HTTP_409_CONFLICT
    elif e.status == 404:
        code = status.HTTP_404_NOT_FOUND
    else:
        # 네이버가 알려준 이유를 그대로 보여준다 — 사용자가 직접 고칠 수 있는 정보다.
        code = status.HTTP_502_BAD_GATEWAY
    return HTTPException(code, str(e))


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
    """4c 검토 화면의 수정 저장. 등록된 상품은 저장 후 '수정'을 눌러야 스토어에 반영된다."""
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

    try:
        result = naver_register(draft)
    except NaverApiError as e:
        raise _http_error(e) from e

    draft.naver_origin_product_no = str(result["originProductNo"])
    draft.naver_channel_product_no = str(result.get("smartstoreChannelProductNo") or "")
    draft.status = "registered"
    draft.registered_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(draft)
    return draft


@router.post("/{draft_id}/update", response_model=ProductDraftOut)
def update(draft_id: str, user: CurrentUser, db: DbSession) -> ProductDraft:
    """등록된 상품에 검토 화면의 내용을 반영한다 (등록된 상품 관리 → 수정)."""
    draft = _get_owned(db, draft_id, user.id)

    try:
        naver_update(draft)
    except NaverApiError as e:
        raise _http_error(e) from e

    # 방금 보낸 설명이 스토어의 새 기준값이다. 다음에 설명을 안 고치면 상세 HTML 을 유지한다.
    draft.analysis = {**(draft.analysis or {}), "naver_description": draft.description}
    db.commit()
    db.refresh(draft)
    return draft


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(draft_id: str, user: CurrentUser, db: DbSession) -> None:
    """스마트스토어에서 상품을 삭제하고 로컬 기록도 지운다 (등록된 상품 관리 → 삭제)."""
    draft = _get_owned(db, draft_id, user.id)

    try:
        naver_delete(draft)
    except NaverApiError as e:
        raise _http_error(e) from e

    # 이 초안을 만든 작업도 지운다 — 남겨 두면 내 작업에 빈 카드로 다시 나타난다.
    for job in db.query(Job).filter(Job.product_draft_id == draft.id).all():
        db.delete(job)
    db.flush()
    db.delete(draft)
    db.commit()
