"""헬스체크. 배포 스크립트와 compose healthcheck 가 사용한다."""

from __future__ import annotations

from fastapi import APIRouter

from ad_service.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }
