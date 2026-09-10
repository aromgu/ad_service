"""``POST /api/v1/generate`` — 생성 작업을 접수하고 202 를 반환한다."""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status
from pydantic import ValidationError as PydanticValidationError

from ad_service.api.errors import PayloadTooLargeError, ValidationError
from ad_service.api.jobs import run_job
from ad_service.api.pipeline import GenerationInput
from ad_service.api.schemas.generation import (
    AcceptedResponse,
    GenerationRequest,
    JobState,
    OutputType,
)
from ad_service.core.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["generation"])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_ASSET_URL_PREFIX = "/api/v1/assets"


def _parse_request(raw: str | None, body: dict | None) -> GenerationRequest:
    payload = body if body is not None else _loads(raw)
    try:
        return GenerationRequest.model_validate(payload)
    except PydanticValidationError as exc:
        details = [
            {"field": ".".join(str(p) for p in err["loc"]), "issue": err["msg"]}
            for err in exc.errors()
        ]
        raise ValidationError("요청 스키마 검증에 실패했습니다", details) from exc


def _loads(raw: str | None) -> dict:
    if not raw:
        raise ValidationError("payload 파트가 비어 있습니다")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"payload JSON 파싱 실패: {exc}") from exc


async def _save_upload(image: UploadFile, dest_dir: Path, max_mb: int) -> Path:
    if image.content_type not in _ALLOWED_IMAGE_TYPES:
        raise ValidationError(f"지원하지 않는 이미지 형식입니다: {image.content_type}")
    data = await image.read()
    if len(data) > max_mb * 1024 * 1024:
        raise PayloadTooLargeError(f"이미지가 {max_mb}MB 를 초과했습니다")
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(image.filename or "upload").suffix or ".png"
    dest = dest_dir / f"input{suffix}"
    dest.write_bytes(data)
    return dest


def _validate_combination(request: GenerationRequest, has_image: bool) -> None:
    """스키마가 볼 수 없는 "text/image 조합" 규칙을 검사한다 (명세서 4.1)."""

    if request.text is None and not has_image:
        raise ValidationError("text 또는 이미지 중 하나는 반드시 필요합니다")
    if OutputType.COPY in request.outputs and request.text is None:
        raise ValidationError("광고 문구(copy) 생성에는 text 가 필요합니다")


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedResponse,
)
async def submit_generation(
    request: Request,
    response: Response,
    payload: Annotated[str | None, Form()] = None,
    image: Annotated[UploadFile | None, File()] = None,
) -> AcceptedResponse:
    settings = get_settings()

    # JSON 요청과 multipart 요청을 모두 받는다.
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = await request.json()
        gen_request = _parse_request(None, body)
    else:
        gen_request = _parse_request(payload, None)

    request_id = gen_request.request_id or secrets.token_hex(8)

    image_path: Path | None = None
    if image is not None:
        image_path = await _save_upload(
            image, settings.upload_root / request_id, settings.max_upload_mb
        )

    _validate_combination(gen_request, has_image=image_path is not None)

    store = request.app.state.job_store
    pipeline = request.app.state.pipeline
    await store.create(request_id)

    output_dir = settings.output_root / request_id
    tasks: set[asyncio.Task] = request.app.state.background_tasks
    task = asyncio.create_task(
        run_job(
            store=store,
            pipeline=pipeline,
            request_id=request_id,
            data=GenerationInput(gen_request, image_path),
            output_dir=output_dir,
            asset_url_prefix=f"{_ASSET_URL_PREFIX}/{request_id}",
        )
    )
    # 태스크가 GC 되지 않도록 참조를 잡아둔다.
    tasks.add(task)
    task.add_done_callback(tasks.discard)

    poll_url = f"/api/v1/jobs/{request_id}"
    response.headers["Location"] = poll_url
    return AcceptedResponse(request_id=request_id, status=JobState.PENDING, poll_url=poll_url)
