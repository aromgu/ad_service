import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    auth,
    documents,
    health,
    jobs,
    products,
    settings as settings_routes,
    uploads,
    workspace,
)
from app.core.config import SHARED_IMAGE_DIR, settings
from app.db.base import init_db
from app.services import job_runner

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    init_db()
    job_runner.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="스마트한 스미스 씨 — Service API",
    description=(
        "상세페이지·상품등록·블로그 생성 서비스의 웹 백엔드. "
        "모델 추론은 generation provider 뒤로 분리돼 있으며 현재는 목업이다."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(uploads.router)
api.include_router(jobs.router)
api.include_router(documents.router)
api.include_router(products.router)
api.include_router(settings_routes.router)
api.include_router(workspace.router)
app.include_router(api)

# 업로드 원본과 web/web-images 공용 이미지를 같은 /static 아래로 서빙한다.
settings.upload_path.mkdir(parents=True, exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory=settings.upload_path), name="uploads")
if SHARED_IMAGE_DIR.is_dir():
    app.mount("/static/images", StaticFiles(directory=SHARED_IMAGE_DIR), name="images")
