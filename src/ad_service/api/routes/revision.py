from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ad_service.api.schemas.revision import (
    RevisionPreviewRequest,
    RevisionPreviewResult,
    RevisionRenderRequest,
    RevisionRenderResult,
)
from ad_service.models.revision_planner import PlanningRequest, PlanningResult, plan_revision
from ad_service.pipelines.revision import (
    RevisionConflict,
    preview_revision,
    render_revision_preview,
)

router = APIRouter(prefix="/v1/detail-pages", tags=["detail-page-editing"])


@router.post("/revision-plan", response_model=PlanningResult)
async def revision_plan(request: PlanningRequest) -> PlanningResult:
    """왼쪽 챗봇의 자연어 지시를 검증된 부분 수정안과 미리보기로 변환한다.

    이미지 편집 실행과 문서 저장은 사용자가 수정안을 확인한 뒤 별도 단계에서 수행한다.
    """
    try:
        return await run_in_threadpool(plan_revision, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="수정 모델을 호출하지 못했습니다.") from exc


@router.post("/revision-preview", response_model=RevisionPreviewResult)
def revision_preview(request: RevisionPreviewRequest) -> RevisionPreviewResult:
    """구조화된 수정안 검증만 수행한다. 모델 호출·저장·이미지 편집은 실행하지 않는다."""
    try:
        return preview_revision(request.document, request.proposal)
    except RevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/revision-render-preview", response_model=RevisionRenderResult)
def revision_render_preview(request: RevisionRenderRequest) -> RevisionRenderResult:
    """승인 전 수정안을 검증하고 실행 코드 없는 HTML 미리보기를 반환한다.

    모델 호출·이미지 편집·파일 저장은 실행하지 않는다. 자산 URL은 프론트가 제공하는
    동일 출처의 안전한 상대 경로만 허용하며, HTML은 격리된 iframe에 표시한다.
    """
    try:
        return render_revision_preview(
            request.document,
            request.proposal,
            request.asset_urls,
        )
    except RevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
