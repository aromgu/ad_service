import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.db.models import Asset
from app.core.config import SHARED_IMAGE_DIR
from app.schemas.common import AssetOut, ImageEditRequest

router = APIRouter(prefix="/uploads", tags=["uploads"])

# 2a 화면 스펙: PNG, JPG, WEBP, 최대 5장
ALLOWED = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAX_FILES = 5
MAX_BYTES = 10 * 1024 * 1024


@router.post("", response_model=list[AssetOut], status_code=status.HTTP_201_CREATED)
async def upload_images(
    user: CurrentUser,
    db: DbSession,
    files: list[UploadFile] = File(...),
) -> list[Asset]:
    if len(files) > MAX_FILES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"이미지는 최대 {MAX_FILES}장까지 올릴 수 있습니다.")

    dest_dir: Path = settings.upload_path
    dest_dir.mkdir(parents=True, exist_ok=True)

    created: list[Asset] = []
    for f in files:
        ext = ALLOWED.get(f.content_type or "")
        if ext is None:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                f"지원하지 않는 형식입니다: {f.content_type}. PNG, JPG, WEBP 만 가능합니다.",
            )
        data = await f.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"{f.filename} 파일이 너무 큽니다. (최대 {MAX_BYTES // 1024 // 1024}MB)",
            )
        name = f"{uuid.uuid4().hex}{ext}"
        (dest_dir / name).write_bytes(data)
        asset = Asset(
            user_id=user.id,
            kind="uploaded",
            filename=f.filename or name,
            url=f"/static/uploads/{name}",
            content_type=f.content_type or "image/png",
            size_bytes=len(data),
        )
        db.add(asset)
        created.append(asset)

    db.commit()
    for a in created:
        db.refresh(a)
    return created


@router.post("/ai-edit", response_model=list[AssetOut], status_code=status.HTTP_201_CREATED)
def ai_edit_images(
    payload: ImageEditRequest,
    user: CurrentUser,
    db: DbSession,
) -> list[Asset]:
    """올린 사진을 블로그용 이미지로 다시 만든다 (3a-2).

    지금은 목업이라 web/web-images 의 생성 샘플을 요청한 장수만큼 돌려준다.
    실제 이미지 생성 모델이 붙으면 이 함수 안만 바꾸면 된다 — prompt 와
    source_ids 는 이미 받아 두었다.
    """
    samples = sorted(p.name for p in SHARED_IMAGE_DIR.glob("serum_gen*.png")) if SHARED_IMAGE_DIR.is_dir() else []
    if not samples:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "샘플 이미지를 찾을 수 없습니다. web/web-images 를 확인해 주세요.",
        )

    created: list[Asset] = []
    for i in range(payload.count):
        name = samples[i % len(samples)]
        asset = Asset(
            user_id=user.id,
            kind="generated",
            filename=name,
            url=f"/static/images/{name}",
            content_type="image/png",
            size_bytes=0,
        )
        db.add(asset)
        created.append(asset)
    db.commit()
    for a in created:
        db.refresh(a)
    return created
