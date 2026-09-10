"""FastAPI 앱 팩토리.

실행: ``uvicorn ad_service.api.main:app --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ad_service.api.errors import register_error_handlers
from ad_service.api.jobs import JobStore
from ad_service.api.pipeline import build_pipeline
from ad_service.api.routes import assets, generate, health, jobs
from ad_service.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="소상공인 맞춤형 광고 문구·이미지 생성 API",
    )

    origins = settings.cors_origins
    allow_all = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # "*" 오리진과 credentials 는 함께 쓸 수 없다.
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 공유 상태: job 저장소와 파이프라인. 실제 모델 연결 시 build_pipeline 만 바뀐다.
    app.state.job_store = JobStore(ttl_seconds=settings.job_ttl_seconds)
    app.state.pipeline = build_pipeline(settings.copy_provider, settings.image_provider)
    # 실행 중인 백그라운드 생성 태스크 참조 보관 (GC 방지).
    app.state.background_tasks = set()

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(generate.router)
    app.include_router(jobs.router)
    app.include_router(assets.router)
    return app


app = create_app()
