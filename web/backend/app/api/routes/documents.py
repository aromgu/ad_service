from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.db.models import Asset, ChatMessage, Document
from app.generation.base import ImageRef
from app.generation.registry import get_provider
from app.schemas.common import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    DocumentOut,
    DocumentPatch,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_owned(db, doc_id: str, user_id: str) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "문서를 찾을 수 없습니다.")
    return doc


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, user: CurrentUser, db: DbSession) -> Document:
    return _get_owned(db, doc_id, user.id)


@router.patch("/{doc_id}", response_model=DocumentOut)
def patch_document(
    doc_id: str, payload: DocumentPatch, user: CurrentUser, db: DbSession
) -> Document:
    """에디터 편집 모드(2d)의 인라인 수정 저장."""
    doc = _get_owned(db, doc_id, user.id)
    if payload.title is not None:
        doc.title = payload.title
    if payload.sections is not None:
        doc.sections = [s.model_dump() for s in payload.sections]
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/{doc_id}/messages", response_model=list[ChatMessageOut])
def list_messages(doc_id: str, user: CurrentUser, db: DbSession) -> list[ChatMessage]:
    doc = _get_owned(db, doc_id, user.id)
    return doc.messages


@router.post("/{doc_id}/chat", response_model=ChatResponse)
def chat(doc_id: str, payload: ChatRequest, user: CurrentUser, db: DbSession) -> ChatResponse:
    """좌측 채팅으로 문서 수정 요청. 목업 규칙 기반 응답."""
    doc = _get_owned(db, doc_id, user.id)

    images: list[ImageRef] = []
    if payload.image_ids:
        rows = (
            db.query(Asset)
            .filter(Asset.id.in_(payload.image_ids), Asset.user_id == user.id)
            .all()
        )
        by_id = {a.id: a for a in rows}
        missing = [i for i in payload.image_ids if i not in by_id]
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "올린 이미지를 찾을 수 없습니다.")
        images = [
            ImageRef(id=i, url=by_id[i].url, filename=by_id[i].filename)
            for i in payload.image_ids
        ]

    user_msg = ChatMessage(
        document_id=doc.id,
        role="user",
        content=payload.message,
        meta={"images": [i.url for i in images]} if images else {},
    )
    db.add(user_msg)

    reply, meta, sections = get_provider().revise(
        message=payload.message, sections=doc.sections, images=images
    )
    doc.sections = sections
    ai_msg = ChatMessage(document_id=doc.id, role="assistant", content=reply, meta=meta)
    db.add(ai_msg)

    db.commit()
    db.refresh(doc)
    db.refresh(user_msg)
    db.refresh(ai_msg)
    return ChatResponse(
        messages=[ChatMessageOut.model_validate(user_msg), ChatMessageOut.model_validate(ai_msg)],
        document=DocumentOut.model_validate(doc),
    )
