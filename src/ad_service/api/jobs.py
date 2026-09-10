"""비동기 생성 job 저장소와 실행기.

MVP 는 단일 프로세스 메모리 dict. API 인스턴스를 2개 이상 띄우면 Redis 로 교체한다
(`docs/api_spec.md` 섹션 5 구현 메모).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from starlette.concurrency import run_in_threadpool

from ad_service.api.errors import APIError
from ad_service.api.metrics import JOB_DURATION, JOBS_IN_PROGRESS, JOBS_TOTAL
from ad_service.api.pipeline import GenerationInput, GenerationPipeline
from ad_service.api.schemas.generation import (
    ErrorBody,
    GenerationResult,
    JobState,
    OutputType,
)


@dataclass
class Job:
    request_id: str
    state: JobState = JobState.PENDING
    progress: float | None = None
    result: GenerationResult | None = None
    error: ErrorBody | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


class JobStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._jobs: dict[str, Job] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def create(self, request_id: str) -> Job:
        async with self._lock:
            self._prune()
            job = Job(request_id=request_id)
            self._jobs[request_id] = job
            return job

    async def get(self, request_id: str) -> Job | None:
        async with self._lock:
            self._prune()
            return self._jobs.get(request_id)

    async def update(self, request_id: str, **changes: object) -> None:
        async with self._lock:
            job = self._jobs.get(request_id)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)

    def _prune(self) -> None:
        now = time.time()
        expired = [
            rid
            for rid, job in self._jobs.items()
            if job.finished_at is not None and now - job.finished_at > self._ttl
        ]
        for rid in expired:
            del self._jobs[rid]


async def run_job(
    store: JobStore,
    pipeline: GenerationPipeline,
    request_id: str,
    data: GenerationInput,
    output_dir: Path,
    asset_url_prefix: str,
) -> None:
    """백그라운드 태스크. job 상태를 갱신하며 파이프라인을 돌린다."""

    started = time.monotonic()
    JOBS_IN_PROGRESS.inc()
    await store.update(request_id, state=JobState.PROCESSING, progress=0.1)
    try:
        result: GenerationResult = await run_in_threadpool(pipeline.generate, data, output_dir)
    except APIError as exc:
        _finish(request_id, "failed", started)
        await store.update(
            request_id,
            state=JobState.FAILED,
            finished_at=time.time(),
            error=ErrorBody(code=exc.code, message=exc.message, details=exc.details),
        )
        return
    except Exception as exc:  # noqa: BLE001 - job 실패는 삼켜서 상태로만 전달
        logger.exception("job {} 실패", request_id)
        _finish(request_id, "failed", started)
        await store.update(
            request_id,
            state=JobState.FAILED,
            finished_at=time.time(),
            error=ErrorBody(code="INTERNAL_ERROR", message=f"생성 중 오류: {exc}"),
        )
        return

    # 자산 URL 을 실제 서빙 경로로 채운다. asset_url_prefix 는 이미 request_id 를 포함한다.
    for asset in result.assets:
        filename = {OutputType.BANNER: "banner.png"}.get(asset.type, f"{asset.type.value}.png")
        asset.url = f"{asset_url_prefix}/{filename}"

    _finish(request_id, "done", started)
    await store.update(
        request_id,
        state=JobState.DONE,
        progress=1.0,
        result=result,
        finished_at=time.time(),
    )


def _finish(request_id: str, status: str, started: float) -> None:
    elapsed = time.monotonic() - started
    JOBS_IN_PROGRESS.dec()
    JOBS_TOTAL.labels(status=status).inc()
    JOB_DURATION.observe(elapsed)
    logger.info("job {} {} ({:.1f}s)", request_id, status, elapsed)
