"""상세페이지 최초 등록, 승인 저장, 불변 버전 조회 API."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from ad_service.api.schemas.detail_page_store import (
    ApproveRevisionRequest,
    RegisterDetailPageRequest,
    RevisionHistoryResult,
    StoredDocumentResult,
    StoredRevisionResult,
)
from ad_service.api.schemas.revision import EditableDocument
from ad_service.core.config import get_settings
from ad_service.pipelines.detail_page_store import (
    DetailPageAlreadyExists,
    DetailPageConflict,
    DetailPageCorrupt,
    DetailPageNotFound,
    approve_detail_page_revision,
    list_detail_page_revisions,
    load_current_detail_page,
    load_detail_page_revision_document,
    load_detail_page_revision_html,
    register_detail_page,
)
from ad_service.pipelines.revision import RevisionConflict

router = APIRouter(prefix="/v1/detail-pages/documents", tags=["detail-page-storage"])


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DetailPageNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(
        exc,
        (DetailPageAlreadyExists, DetailPageConflict, DetailPageCorrupt, RevisionConflict),
    ):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.post("", response_model=StoredRevisionResult, status_code=201)
async def create_detail_page_document(
    request: RegisterDetailPageRequest,
) -> StoredRevisionResult:
    """생성·검토가 끝난 최초 문서와 HTML을 첫 불변 버전으로 등록한다."""
    try:
        return await run_in_threadpool(
            register_detail_page,
            request,
            get_settings().output_root,
        )
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc


@router.get("/{document_id}", response_model=StoredDocumentResult)
def current_detail_page_document(document_id: str) -> StoredDocumentResult:
    try:
        return load_current_detail_page(get_settings().output_root, document_id)
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc


@router.get("/{document_id}/revisions", response_model=RevisionHistoryResult)
def detail_page_revision_history(document_id: str) -> RevisionHistoryResult:
    try:
        return list_detail_page_revisions(get_settings().output_root, document_id)
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc


@router.post("/{document_id}/approve", response_model=StoredRevisionResult, status_code=201)
async def approve_detail_page_document_revision(
    document_id: str,
    request: ApproveRevisionRequest,
) -> StoredRevisionResult:
    """사용자가 승인한 미리보기 해시가 일치할 때만 새 버전을 저장한다."""
    try:
        return await run_in_threadpool(
            approve_detail_page_revision,
            document_id,
            request,
            get_settings().output_root,
        )
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc


@router.get("/{document_id}/revisions/{revision}/document", response_model=EditableDocument)
def detail_page_revision_document(document_id: str, revision: int) -> EditableDocument:
    try:
        return load_detail_page_revision_document(
            get_settings().output_root,
            document_id,
            revision,
        )
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc


@router.get("/{document_id}/revisions/{revision}/html", response_class=HTMLResponse)
def detail_page_revision_html(document_id: str, revision: int) -> HTMLResponse:
    try:
        html = load_detail_page_revision_html(
            get_settings().output_root,
            document_id,
            revision,
        )
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
