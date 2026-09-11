"""상세페이지 이미지 편집의 작업 등록·승인 실행·결과 조회 API."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from ad_service.api.schemas.detail_page_store import StoredRevisionResult
from ad_service.api.schemas.image_edit_job import (
    ApproveImageEditAttachmentRequest,
    ApproveImageEditJobRequest,
    CreateImageEditJobRequest,
    ImageEditAttachmentPreview,
    ImageEditJobResult,
)
from ad_service.core.budget import BudgetExceededError
from ad_service.core.config import get_settings
from ad_service.pipelines.detail_page_store import DetailPageNotFound
from ad_service.pipelines.image_edit_job import (
    ImageEditJobConflict,
    ImageEditJobExecutionError,
    ImageEditJobNotFound,
    ImageEditJobUnsupported,
    approve_and_execute_image_edit_job,
    approve_image_edit_attachment,
    create_image_edit_job,
    load_image_edit_job,
    load_image_edit_result_path,
    preview_image_edit_attachment,
)

router = APIRouter(prefix="/v1/detail-pages", tags=["detail-page-image-editing"])


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (DetailPageNotFound, ImageEditJobNotFound)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ImageEditJobConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, BudgetExceededError):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, ImageEditJobExecutionError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ImageEditJobUnsupported):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/documents/{document_id}/image-edit-jobs",
    response_model=ImageEditJobResult,
    status_code=201,
)
async def register_image_edit_job(
    document_id: str,
    request: CreateImageEditJobRequest,
) -> ImageEditJobResult:
    """편집 사양과 비용을 보여 줄 작업만 등록하며 이미지 모델은 호출하지 않는다."""

    settings = get_settings()
    try:
        return await run_in_threadpool(
            create_image_edit_job,
            document_id,
            request,
            settings.output_root,
            settings.image_provider,
            settings.image_quality,
        )
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc


@router.get("/image-edit-jobs/{job_id}", response_model=ImageEditJobResult)
def image_edit_job(job_id: str) -> ImageEditJobResult:
    try:
        return load_image_edit_job(get_settings().output_root, job_id)
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc


@router.post("/image-edit-jobs/{job_id}/approve", response_model=ImageEditJobResult)
async def approve_image_edit_job(
    job_id: str,
    request: ApproveImageEditJobRequest,
) -> ImageEditJobResult:
    """사용자 승인을 검증한 뒤에만 이미지 모델을 한 번 호출한다."""

    settings = get_settings()
    try:
        return await run_in_threadpool(
            approve_and_execute_image_edit_job,
            job_id,
            request,
            settings.output_root,
            settings.budget_cap_usd,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        raise _translate_error(exc) from exc


@router.get("/image-edit-jobs/{job_id}/result", response_class=FileResponse)
def image_edit_job_result(job_id: str) -> FileResponse:
    try:
        path = load_image_edit_result_path(get_settings().output_root, job_id)
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc
    return FileResponse(
        path,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/image-edit-jobs/{job_id}/attachment-preview",
    response_model=ImageEditAttachmentPreview,
)
async def image_edit_attachment_preview(job_id: str) -> ImageEditAttachmentPreview:
    """편집 결과를 새 자산으로 연결한 문서·HTML을 저장 없이 미리 보여 준다."""

    try:
        return await run_in_threadpool(
            preview_image_edit_attachment,
            get_settings().output_root,
            job_id,
        )
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/image-edit-jobs/{job_id}/attach",
    response_model=StoredRevisionResult,
    status_code=201,
)
async def attach_image_edit_result(
    job_id: str,
    request: ApproveImageEditAttachmentRequest,
) -> StoredRevisionResult:
    """사용자가 확인한 이미지·문서·HTML 해시가 모두 일치할 때 새 버전으로 저장한다."""

    try:
        return await run_in_threadpool(
            approve_image_edit_attachment,
            job_id,
            request,
            get_settings().output_root,
        )
    except (ValueError, OSError) as exc:
        raise _translate_error(exc) from exc
