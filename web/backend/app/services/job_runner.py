"""인프로세스 생성 작업 실행기.

작업을 asyncio 태스크로 돌리면서 진행률을 DB(jobs 테이블)에 기록한다.
프론트는 GET /api/jobs/{id} 를 폴링해 2b 화면을 갱신한다.

주의: 워커가 여러 프로세스로 늘어나면(gunicorn -w N) 태스크 레지스트리가
프로세스별로 쪼개진다. 그 시점엔 Celery/RQ 같은 외부 큐로 옮겨야 한다.
지금은 단일 uvicorn 프로세스 전제.
"""

import asyncio
import logging
from concurrent.futures import Future

from app.db.base import SessionLocal
from app.db.models import utcnow
from app.db.models import ChatMessage, Document, Job, ProductDraft
from app.generation.base import DocumentDraft, ImageRef, ProductDraftData
from app.generation.registry import get_provider

logger = logging.getLogger(__name__)

_tasks: dict[str, "asyncio.Task | Future"] = {}
# 라우터 핸들러는 스레드풀에서 도는 sync 함수라 running loop 가 없다.
# 앱 기동 시 메인 이벤트 루프를 잡아 두고 거기에 작업을 밀어 넣는다.
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _mark_steps(steps: list[dict], active_key: str | None, *, finished: bool = False) -> list[dict]:
    """active_key 이전 스텝은 done, 해당 스텝은 active, 이후는 pending."""
    out: list[dict] = []
    seen_active = False
    for s in steps:
        step = dict(s)
        if finished:
            step["state"] = "done"
        elif seen_active:
            step["state"] = "pending"
        elif step["key"] == active_key:
            step["state"] = "active"
            seen_active = True
        else:
            step["state"] = "done"
        out.append(step)
    return out


def _save_document(db, job: Job, draft: DocumentDraft) -> str:
    doc = Document(
        user_id=job.user_id,
        type=job.type,
        title=draft.title,
        sections=draft.sections,
        thumbnail_url=draft.thumbnail_url,
    )
    db.add(doc)
    db.flush()
    for m in draft.messages:
        db.add(
            ChatMessage(
                document_id=doc.id,
                role=m["role"],
                content=m["content"],
                meta=m.get("meta", {}),
            )
        )
    return doc.id


def _save_product_draft(db, job: Job, data: ProductDraftData) -> ProductDraft:
    """상품등록 결과 저장.

    4a 에서 "AI가 알아서 등록하기"를 눌렀다면(submit_mode='auto') 4c 검토 화면을
    건너뛰고 여기서 바로 등록 상태로 만든다.
    """
    form = job.form or {}
    draft = ProductDraft(
        user_id=job.user_id,
        analysis=data.analysis,
        description=data.description,
        image_urls=data.image_urls,
        representative_image_url=data.representative_image_url,
        product_name=data.product_name,
        brand=data.brand,
        manufacturer=data.manufacturer,
        seller_code=data.seller_code,
        category_candidates=data.category_candidates,
        selected_category=data.selected_category,
        price=data.price,
        shipping_fee=data.shipping_fee,
        stock=data.stock,
        options=data.options,
        kc=data.kc,
        tags=data.tags,
        attributes=data.attributes,
        shipping=form.get("shipping") or {},
    )
    if form.get("submit_mode") == "auto":
        draft.status = "registered"
        draft.registered_at = utcnow()
    db.add(draft)
    db.flush()
    return draft


async def _run(job_id: str, images: list[ImageRef]) -> None:
    provider = get_provider()
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = "running"
        db.commit()

        async def on_progress(step_key: str | None, ratio: float) -> None:
            # 콜백마다 세션을 새로 열지 않고 같은 세션에 쓴다(단일 태스크 전제).
            j = db.get(Job, job_id)
            if j is None or j.status == "canceled":
                return
            j.progress = round(min(max(ratio, 0.0), 1.0) * 100, 1)
            j.steps = _mark_steps(j.steps, step_key)
            db.commit()

        result = await provider.generate(
            job_type=job.type,
            form=job.form or {},
            images=images,
            on_progress=on_progress,
        )

        doc_id: str | None = None
        draft_id: str | None = None

        if isinstance(result, ProductDraftData):
            draft = _save_product_draft(db, job, result)
            draft_id = draft.id
        elif isinstance(result, DocumentDraft):
            doc_id = _save_document(db, job, result)
        else:  # pragma: no cover — provider 계약 위반
            raise TypeError(f"알 수 없는 생성 결과 타입: {type(result)!r}")

        job = db.get(Job, job_id)
        if job is not None and job.status != "canceled":
            job.document_id = doc_id
            job.product_draft_id = draft_id
            job.status = "done"
            job.progress = 100.0
            job.steps = _mark_steps(job.steps, None, finished=True)
        db.commit()

    except asyncio.CancelledError:
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None and job.status not in ("done", "failed"):
            job.status = "canceled"
            db.commit()
        raise
    except Exception as exc:  # noqa: BLE001 — 작업 실패는 상태로 표현한다
        logger.exception("생성 작업 실패: %s", job_id)
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)
            db.commit()
    finally:
        db.close()
        _tasks.pop(job_id, None)


def start(job_id: str, images: list[ImageRef]) -> None:
    if job_id in _tasks:
        return
    coro = _run(job_id, images)
    try:
        _tasks[job_id] = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        if _loop is None:
            coro.close()
            raise RuntimeError("job_runner.bind_loop() 가 호출되지 않았습니다.") from None
        _tasks[job_id] = asyncio.run_coroutine_threadsafe(coro, _loop)


def cancel(job_id: str) -> bool:
    task = _tasks.get(job_id)
    if task is None:
        return False
    task.cancel()
    return True
