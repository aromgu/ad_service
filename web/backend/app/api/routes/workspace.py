from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.db.models import Document, Job, ProductDraft
from app.schemas.common import WorkspaceItem

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=list[WorkspaceItem])
def list_items(
    user: CurrentUser,
    db: DbSession,
    type: str | None = Query(default=None, description="detail_page | product_reg | blog"),
    limit: int = Query(default=50, le=200),
) -> list[WorkspaceItem]:
    """내 작업(5a) 목록. 생성 중·실패한 작업도 카드로 함께 내려준다.

    스마트스토어에 등록까지 끝난 상품은 '등록된 상품 관리'에서 다루므로 여기선 뺀다.
    """
    q = db.query(Job).filter(Job.user_id == user.id)
    if type:
        q = q.filter(Job.type == type)
    jobs = q.order_by(Job.created_at.desc()).limit(limit).all()

    doc_ids = [j.document_id for j in jobs if j.document_id]
    docs = {
        d.id: d for d in (db.query(Document).filter(Document.id.in_(doc_ids)).all() if doc_ids else [])
    }
    draft_ids = [j.product_draft_id for j in jobs if j.product_draft_id]
    drafts = {
        d.id: d
        for d in (
            db.query(ProductDraft).filter(ProductDraft.id.in_(draft_ids)).all() if draft_ids else []
        )
    }

    items: list[WorkspaceItem] = []
    for j in jobs:
        doc = docs.get(j.document_id) if j.document_id else None
        draft = drafts.get(j.product_draft_id) if j.product_draft_id else None
        if draft is not None and draft.status == "registered":
            continue
        items.append(
            WorkspaceItem(
                id=(doc.id if doc else draft.id if draft else j.id),
                job_id=j.id,
                document_id=j.document_id,
                product_draft_id=j.product_draft_id,
                type=j.type,
                status=j.status,
                progress=j.progress,
                title=_title_of(j, doc, draft),
                thumbnail_url=(
                    doc.thumbnail_url if doc else draft.representative_image_url if draft else None
                ),
                created_at=j.created_at,
            )
        )
    return items


def _title_of(job: Job, doc, draft) -> str:
    if doc is not None:
        return doc.title
    if draft is not None:
        return draft.title or draft.product_name or "상품등록"
    form = job.form or {}
    return form.get("product_name") or form.get("topic") or "제목 없음"


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(job_id: str, user: CurrentUser, db: DbSession) -> None:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다.")
    doc = db.get(Document, job.document_id) if job.document_id else None
    draft = db.get(ProductDraft, job.product_draft_id) if job.product_draft_id else None
    # 참조하는 FK 를 먼저 끊고 삭제한다.
    job.document_id = None
    job.product_draft_id = None
    db.flush()
    if doc is not None:
        db.delete(doc)
    if draft is not None:
        db.delete(draft)
    db.delete(job)
    db.commit()
