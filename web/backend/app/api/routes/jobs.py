from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.db.models import Asset, Document, Job
from app.generation.base import ImageRef
from app.generation.registry import get_provider
from app.schemas.common import JobCreate, JobOut
from app.services import job_runner

router = APIRouter(prefix="/jobs", tags=["jobs"])

# 타입별 이미지 장수 규칙 (와이어프레임 2a / 3a / 4a)
IMAGE_RULES = {
    "detail_page": (1, 5, "상품 이미지를 1장 이상 올려주세요. (최대 5장)"),
    "blog": (1, 8, "블로그에 넣을 사진을 1장 이상 올려주세요. (최대 8장)"),
    "product_reg": (1, 20, "상세페이지 이미지를 1장 이상 올려주세요."),
}


def _load_images(db, user_id: str, image_ids: list[str]) -> list[ImageRef]:
    if not image_ids:
        return []
    rows = db.query(Asset).filter(Asset.id.in_(image_ids), Asset.user_id == user_id).all()
    by_id = {a.id: a for a in rows}
    missing = [i for i in image_ids if i not in by_id]
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"존재하지 않는 이미지입니다: {missing[0]}")
    # 사용자가 올린 순서를 유지한다.
    return [ImageRef(id=i, url=by_id[i].url, filename=by_id[i].filename) for i in image_ids]


def _images_from_document(db, doc_id: str, user_id: str) -> list[ImageRef]:
    """2c 에디터에서 넘어온 경우 — 문서에 배치된 이미지를 그대로 이어 쓴다."""
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "상세페이지를 찾을 수 없습니다.")
    urls = [
        s["content"]["url"]
        for s in doc.sections
        if s.get("type") == "image" and s.get("content", {}).get("url")
    ]
    return [ImageRef(id=f"doc-{i}", url=u) for i, u in enumerate(urls)]


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, user: CurrentUser, db: DbSession) -> JobOut:
    from_doc = getattr(payload, "from_document_id", None)

    if from_doc:
        images = _images_from_document(db, from_doc, user.id)
        if not images:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "이 상세페이지에는 넘길 이미지가 없습니다."
            )
    else:
        low, high, message = IMAGE_RULES[payload.type]
        if not (low <= len(payload.image_ids) <= high):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, message)
        images = _load_images(db, user.id, payload.image_ids)

    steps = [{**s, "state": "pending"} for s in get_provider().steps(payload.type)]
    job = Job(
        user_id=user.id,
        type=payload.type,
        status="queued",
        progress=0.0,
        steps=steps,
        form=payload.form.model_dump(),
        image_ids=payload.image_ids,
        source_document_id=from_doc,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    job_runner.start(job.id, images)
    return JobOut.from_job(job)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: CurrentUser, db: DbSession) -> JobOut:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다.")
    return JobOut.from_job(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, user: CurrentUser, db: DbSession) -> JobOut:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다.")
    if job.status in ("done", "failed", "canceled"):
        return JobOut.from_job(job)
    job.status = "canceled"
    db.commit()
    db.refresh(job)
    job_runner.cancel(job_id)
    return JobOut.from_job(job)


@router.post("/{job_id}/retry", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def retry_job(job_id: str, user: CurrentUser, db: DbSession) -> JobOut:
    """같은 입력값으로 다시 생성한다 (내 작업 5a 의 '다시 시도').

    원본 작업은 그대로 두고 새 작업을 만든다 — 실패 기록을 지우지 않기 위해서다.
    """
    origin = db.get(Job, job_id)
    if origin is None or origin.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다.")

    if origin.source_document_id:
        images = _images_from_document(db, origin.source_document_id, user.id)
    else:
        images = _load_images(db, user.id, origin.image_ids or [])
    if not images:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "원본 이미지가 남아 있지 않아 다시 시도할 수 없습니다. 처음부터 다시 만들어 주세요.",
        )

    steps = [{**s, "state": "pending"} for s in get_provider().steps(origin.type)]
    job = Job(
        user_id=user.id,
        type=origin.type,
        status="queued",
        progress=0.0,
        steps=steps,
        form=origin.form,
        image_ids=origin.image_ids,
        source_document_id=origin.source_document_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    job_runner.start(job.id, images)
    return JobOut.from_job(job)
