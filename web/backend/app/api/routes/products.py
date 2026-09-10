from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.korean import eul_reul
from app.db.models import ProductDraft
from app.schemas.common import ProductDraftOut, ProductDraftPatch

router = APIRouter(prefix="/product-drafts", tags=["products"])

# 카테고리 직접 검색(4c)용 목업 사전. 실제로는 네이버 커머스 카테고리 API 를 호출한다.
_CATEGORY_BOOK = [
    "패션잡화 › 여성가방 › 에코백",
    "패션잡화 › 여성가방 › 크로스백",
    "패션잡화 › 남성가방 › 에코백",
    "출산/육아 › 유아동잡화 › 가방 › 토트백/숄더백",
    "생활/건강 › 문구/사무용품 › 노트/메모지",
    "생활/건강 › 생활용품 › 수납/정리",
    "화장품/미용 › 스킨케어 › 에센스/세럼",
    "화장품/미용 › 스킨케어 › 크림",
    "식품 › 가공식품 › 간편조리식품",
    "디지털/가전 › 주변기기 › 마우스패드",
]


def _get_owned(db, draft_id: str, user_id: str) -> ProductDraft:
    draft = db.get(ProductDraft, draft_id)
    if draft is None or draft.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록 정보를 찾을 수 없습니다.")
    return draft


@router.get("/categories/search", response_model=list[str])
def search_categories(q: str = Query(min_length=1, max_length=60)) -> list[str]:
    """카테고리 직접 검색. 지금은 내장 사전에서 부분 일치로 찾는다."""
    needle = q.strip()
    return [c for c in _CATEGORY_BOOK if needle in c][:8]


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
    """네이버에 상품 등록.

    실제 커머스 API 연동은 아직 붙이지 않았다. 지금은 필수값을 검증하고
    상태만 registered 로 바꾼다. 연동 시 이 함수 안에서 토큰 발급 → 상품 등록을
    호출하면 되고, 호출부(프론트)는 바뀌지 않는다.
    """
    draft = _get_owned(db, draft_id, user.id)

    missing: list[str] = []
    if not draft.product_name.strip():
        missing.append("상품명")
    if not draft.selected_category.strip():
        missing.append("카테고리")
    if draft.price is None or draft.price <= 0:
        missing.append("판매가")
    if missing:
        # 마지막 항목에만 조사를 붙인다. "상품명, 판매가를 먼저 입력해 주세요."
        listed = ", ".join(missing[:-1] + [eul_reul(missing[-1])])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{listed} 먼저 입력해 주세요.")

    draft.status = "registered"
    draft.registered_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(draft)
    return draft
