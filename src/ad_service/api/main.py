from fastapi import FastAPI

from ad_service.api.routes.generate import router as generation_router
from ad_service.api.routes.health import router as health_router
from ad_service.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="한국어 광고 문구와 원본 보존형 광고 이미지를 생성하는 모델 API",
    )
    app.include_router(health_router)
    app.include_router(generation_router)
    return app


app = create_app()
