from fastapi import FastAPI

from ad_service.api.routes.demo import router as demo_router
from ad_service.api.routes.detail_page import router as detail_page_router
from ad_service.api.routes.detail_page_copy import router as detail_page_copy_router
from ad_service.api.routes.detail_page_plan import router as detail_page_plan_router
from ad_service.api.routes.detail_page_store import router as detail_page_store_router
from ad_service.api.routes.editor import router as editor_router
from ad_service.api.routes.generate import router as generation_router
from ad_service.api.routes.generation_job import router as generation_job_router
from ad_service.api.routes.health import router as health_router
from ad_service.api.routes.image_edit_job import router as image_edit_job_router
from ad_service.api.routes.revision import router as revision_router
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
    app.include_router(generation_job_router)
    app.include_router(demo_router)
    app.include_router(editor_router)
    app.include_router(detail_page_router)
    app.include_router(detail_page_copy_router)
    app.include_router(detail_page_plan_router)
    app.include_router(detail_page_store_router)
    app.include_router(revision_router)
    app.include_router(image_edit_job_router)
    return app


app = create_app()
