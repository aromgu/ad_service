"""``GET /api/v1/assets/{request_id}/{filename}`` — 생성된 이미지 파일 반환."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from ad_service.api.errors import NotFoundError, ValidationError
from ad_service.core.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["generation"])

_REQUEST_ID = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
_FILENAME = re.compile(r"^[a-zA-Z0-9_-]+\.(png|jpg|jpeg|webp)$")
_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


@router.get("/assets/{request_id}/{filename}")
def get_asset(request: Request, request_id: str, filename: str) -> FileResponse:
    # 경로 탈출 방지: 두 세그먼트 모두 화이트리스트 패턴만 허용.
    if not _REQUEST_ID.match(request_id) or not _FILENAME.match(filename):
        raise ValidationError("잘못된 자산 경로입니다")

    settings = get_settings()
    path = (settings.output_root / request_id / filename).resolve()
    root = settings.output_root.resolve()
    if root not in path.parents or not path.is_file():
        raise NotFoundError("자산을 찾을 수 없습니다")

    ext = filename.rsplit(".", 1)[1].lower()
    return FileResponse(path, media_type=_MEDIA_TYPES[ext])
