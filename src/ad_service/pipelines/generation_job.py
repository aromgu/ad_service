"""생성 파이프라인을 백그라운드에서 실행하고 실제 상태를 영속화한다."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import queue
import re
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from ad_service.api.schemas.generation import GenerationRequest, GenerationResult, OutputType
from ad_service.api.schemas.generation_job import (
    CreateGenerationJobRequest,
    GenerationJobEvent,
    GenerationJobEventsResult,
    GenerationJobResult,
    GenerationJobStatus,
    RetryGenerationJobRequest,
)
from ad_service.core.budget import BudgetExceededError
from ad_service.core.progress import (
    GenerationCancelledError,
    PipelineProgress,
    PipelineStage,
)
from ad_service.pipelines.inference import GenerationPipeline

IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
STORE_NAME = "_generation_jobs"
TERMINAL_STATUSES = {
    GenerationJobStatus.SUCCEEDED.value,
    GenerationJobStatus.FAILED.value,
    GenerationJobStatus.CANCELLED.value,
}
PipelineFactory = Callable[[], GenerationPipeline]


class GenerationJobError(ValueError):
    pass


class GenerationJobNotFound(GenerationJobError):
    pass


class GenerationJobConflict(GenerationJobError):
    pass


class GenerationJobCorrupt(GenerationJobError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(value) -> bytes:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())


def _replace_json(path: Path, value: dict) -> None:
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        _write_new(temporary, _canonical_bytes(value))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise GenerationJobCorrupt("생성 작업 저장 파일을 읽을 수 없습니다")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GenerationJobCorrupt("생성 작업 저장 파일을 읽을 수 없습니다") from exc
    if not isinstance(value, dict):
        raise GenerationJobCorrupt("생성 작업 저장 형식이 잘못되었습니다")
    return value


@contextmanager
def _locked(path: Path):
    if path.is_symlink():
        raise GenerationJobCorrupt("생성 작업 잠금 파일을 사용할 수 없습니다")
    with path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class GenerationJobService:
    """단일 워커로 비용 원장 충돌을 피하면서 생성 작업을 순서대로 실행한다."""

    def __init__(
        self,
        output_root: Path,
        pipeline_factory: PipelineFactory,
        *,
        base_dir: Path | None = None,
    ) -> None:
        self.output_root = output_root.expanduser().resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.store_root = self.output_root / STORE_NAME
        if self.store_root.is_symlink():
            raise GenerationJobCorrupt("생성 작업 저장소 심볼릭 링크는 사용할 수 없습니다")
        self.store_root.mkdir(exist_ok=True)
        self.pipeline_factory = pipeline_factory
        self.base_dir = (base_dir or Path.cwd()).resolve()
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._scheduled: set[str] = set()
        self._scheduled_lock = threading.Lock()
        self._worker = threading.Thread(
            target=self._work,
            name="ad-service-generation-worker",
            daemon=True,
        )
        self._worker.start()
        self._recover_jobs()

    def _directory(self, job_id: str, *, required: bool = True) -> Path:
        if not IDENTIFIER.fullmatch(job_id) or job_id == STORE_NAME:
            raise GenerationJobNotFound("생성 작업을 찾을 수 없습니다")
        directory = self.store_root / job_id
        if directory.is_symlink():
            raise GenerationJobNotFound("생성 작업을 찾을 수 없습니다")
        if required and not directory.is_dir():
            raise GenerationJobNotFound("생성 작업을 찾을 수 없습니다")
        return directory

    def _state(self, job_id: str) -> dict:
        return _read_json(self._directory(job_id) / "job.json")

    @staticmethod
    def _public(state: dict, *, replayed: bool = False) -> GenerationJobResult:
        fields = GenerationJobResult.model_fields
        payload = {name: state.get(name) for name in fields if name not in {"replayed"}}
        status = state.get("status")
        payload.update(
            {
                "can_cancel": status
                in {
                    GenerationJobStatus.QUEUED.value,
                    GenerationJobStatus.RUNNING.value,
                },
                "can_retry": status == GenerationJobStatus.CANCELLED.value
                or (
                    status == GenerationJobStatus.FAILED.value
                    and bool((state.get("error") or {}).get("retryable"))
                ),
                "replayed": replayed,
                "persisted": True,
            }
        )
        return GenerationJobResult.model_validate(payload)

    @staticmethod
    def _event(
        sequence: int,
        status: str,
        stage: str,
        message: str,
        *,
        asset_type: str | None = None,
        completed_assets: int | None = None,
        total_assets: int | None = None,
    ) -> dict:
        return {
            "sequence": sequence,
            "status": status,
            "stage": stage,
            "message": message,
            "created_at": _now(),
            "progress_percent": None,
            "estimated_remaining_ms": None,
            "asset_type": asset_type,
            "completed_assets": completed_assets,
            "total_assets": total_assets,
        }

    def create(
        self,
        request: CreateGenerationJobRequest,
        *,
        retry_of: str | None = None,
        attempt: int = 1,
    ) -> GenerationJobResult:
        job_id = request.request.request_id
        if job_id == STORE_NAME:
            raise GenerationJobConflict("예약된 request_id는 사용할 수 없습니다")
        request_sha256 = _sha256(_canonical_bytes(request.request))
        create_sha256 = _sha256(
            _canonical_bytes(
                {
                    # dict 안의 모델은 _canonical_bytes 가 펴주지 못하므로 미리 편다.
                    "request": request.request.model_dump(mode="json"),
                    "seed": request.seed,
                    "retry_of": retry_of,
                    "attempt": attempt,
                }
            )
        )
        directory = self._directory(job_id, required=False)

        with _locked(self.store_root / ".store.lock"):
            if directory.exists():
                if not directory.is_dir():
                    raise GenerationJobConflict("동일한 생성 작업 ID를 사용할 수 없습니다")
                state = _read_json(directory / "job.json")
                if state.get("_create_sha256") != create_sha256:
                    raise GenerationJobConflict("동일한 request_id에 다른 생성 요청이 존재합니다")
                result = self._public(state, replayed=True)
            else:
                run_directory = self.output_root / job_id
                if run_directory.exists() or run_directory.is_symlink():
                    raise GenerationJobConflict(
                        "request_id와 같은 기존 결과 폴더가 있어 새 작업을 만들 수 없습니다"
                    )
                staging = self.store_root / f".pending-{job_id}-{uuid4().hex}"
                staging.mkdir()
                try:
                    created_at = _now()
                    total_assets = sum(
                        output is not OutputType.COPY for output in request.request.outputs
                    )
                    event = self._event(
                        1,
                        GenerationJobStatus.QUEUED.value,
                        PipelineStage.QUEUED.value,
                        "생성 작업이 대기열에 등록되었습니다.",
                        completed_assets=0,
                        total_assets=total_assets,
                    )
                    state = {
                        "schema_version": "generation-job-0.1",
                        "job_id": job_id,
                        "request_id": job_id,
                        "request_sha256": request_sha256,
                        "retry_of": retry_of,
                        "attempt": attempt,
                        "status": GenerationJobStatus.QUEUED.value,
                        "stage": PipelineStage.QUEUED.value,
                        "sequence": 1,
                        "message": event["message"],
                        "progress_percent": None,
                        "estimated_remaining_ms": None,
                        "completed_assets": 0,
                        "total_assets": total_assets,
                        "model_calls": 0,
                        "image_generation_calls": 0,
                        "preprocessing_calls": 0,
                        "recorded_cost_usd": 0.0,
                        "created_at": created_at,
                        "started_at": None,
                        "updated_at": created_at,
                        "cancel_requested_at": None,
                        "finished_at": None,
                        "result_url": None,
                        "error": None,
                        "_create_sha256": create_sha256,
                        "_seed": request.seed,
                        "_events": [event],
                    }
                    _write_new(staging / "request.json", _canonical_bytes(request.request))
                    _write_new(staging / "job.json", _canonical_bytes(state))
                    os.replace(staging, directory)
                finally:
                    if staging.exists():
                        shutil.rmtree(staging)
                result = self._public(state)

        if result.status is GenerationJobStatus.QUEUED:
            self._submit(job_id)
        return result

    def load(self, job_id: str) -> GenerationJobResult:
        return self._public(self._state(job_id))

    def events(self, job_id: str, after_sequence: int = 0) -> GenerationJobEventsResult:
        state = self._state(job_id)
        raw_events = state.get("_events")
        if not isinstance(raw_events, list):
            raise GenerationJobCorrupt("생성 작업 이벤트 기록이 잘못되었습니다")
        try:
            events = [GenerationJobEvent.model_validate(item) for item in raw_events]
        except ValueError as exc:
            raise GenerationJobCorrupt("생성 작업 이벤트 기록이 잘못되었습니다") from exc
        items = [item for item in events if item.sequence > after_sequence]
        return GenerationJobEventsResult(
            job_id=job_id,
            latest_sequence=state["sequence"],
            items=items,
        )

    def cancel(self, job_id: str) -> GenerationJobResult:
        directory = self._directory(job_id)
        with _locked(directory / ".write.lock"):
            state = _read_json(directory / "job.json")
            status = state.get("status")
            if status in {
                GenerationJobStatus.CANCEL_REQUESTED.value,
                GenerationJobStatus.CANCELLED.value,
            }:
                return self._public(state, replayed=True)
            if status in {
                GenerationJobStatus.SUCCEEDED.value,
                GenerationJobStatus.FAILED.value,
            }:
                raise GenerationJobConflict("완료된 생성 작업은 취소할 수 없습니다")

            now = _now()
            state["sequence"] += 1
            if status == GenerationJobStatus.QUEUED.value:
                state.update(
                    {
                        "status": GenerationJobStatus.CANCELLED.value,
                        "message": "모델 호출 전에 생성 작업을 취소했습니다.",
                        "cancel_requested_at": now,
                        "finished_at": now,
                        "updated_at": now,
                    }
                )
            else:
                state.update(
                    {
                        "status": GenerationJobStatus.CANCEL_REQUESTED.value,
                        "message": "취소 요청을 접수했습니다. 현재 호출 뒤 안전하게 중단합니다.",
                        "cancel_requested_at": state.get("cancel_requested_at") or now,
                        "updated_at": now,
                    }
                )
            state["_events"].append(
                self._event(
                    state["sequence"],
                    state["status"],
                    state["stage"],
                    state["message"],
                    completed_assets=state["completed_assets"],
                    total_assets=state["total_assets"],
                )
            )
            _replace_json(directory / "job.json", state)
            return self._public(state)

    def retry(
        self,
        job_id: str,
        request: RetryGenerationJobRequest,
    ) -> GenerationJobResult:
        state = self._state(job_id)
        if state.get("status") not in {
            GenerationJobStatus.FAILED.value,
            GenerationJobStatus.CANCELLED.value,
        }:
            raise GenerationJobConflict("실패하거나 취소된 생성 작업만 재시도할 수 있습니다")
        if state["status"] == GenerationJobStatus.FAILED.value and not bool(
            (state.get("error") or {}).get("retryable")
        ):
            raise GenerationJobConflict(
                "재시도할 수 없는 실패입니다. 입력을 수정해 새로 요청하세요"
            )
        old_request = GenerationRequest.model_validate(
            _read_json(self._directory(job_id) / "request.json")
        )
        new_request = old_request.model_copy(update={"request_id": request.new_request_id})
        return self.create(
            CreateGenerationJobRequest(request=new_request, seed=state["_seed"]),
            retry_of=job_id,
            attempt=state["attempt"] + 1,
        )

    def result(self, job_id: str) -> GenerationResult:
        state = self._state(job_id)
        if state.get("status") != GenerationJobStatus.SUCCEEDED.value:
            raise GenerationJobConflict("성공한 생성 작업만 결과를 조회할 수 있습니다")
        result_path = self.output_root / job_id / "result.json"
        try:
            return GenerationResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GenerationJobCorrupt("생성 결과 파일을 읽을 수 없습니다") from exc

    def shutdown(self, timeout: float = 2.0) -> None:
        self._queue.put(None)
        self._worker.join(timeout=timeout)

    def _submit(self, job_id: str) -> None:
        with self._scheduled_lock:
            if job_id in self._scheduled:
                return
            self._scheduled.add(job_id)
        self._queue.put(job_id)

    def _work(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                self._queue.task_done()
                return
            try:
                self._run(job_id)
            finally:
                with self._scheduled_lock:
                    self._scheduled.discard(job_id)
                self._queue.task_done()

    def _run(self, job_id: str) -> None:
        if not self._start(job_id):
            return
        try:
            request = GenerationRequest.model_validate(
                _read_json(self._directory(job_id) / "request.json")
            )
            result = self.pipeline_factory().generate(
                request,
                self._state(job_id)["_seed"],
                self.base_dir,
                progress_callback=lambda progress: self._record_progress(job_id, progress),
                cancellation_check=lambda: self._cancel_requested(job_id),
            )
            if self._cancel_requested(job_id):
                self._finish_cancelled(job_id)
            else:
                self._finish_succeeded(job_id, result)
        except GenerationCancelledError:
            self._finish_cancelled(job_id)
        except BudgetExceededError as exc:
            self._finish_failed(job_id, "budget_exceeded", str(exc), retryable=False)
        except FileNotFoundError as exc:
            self._finish_failed(job_id, "input_file_missing", str(exc), retryable=False)
        except ValueError as exc:
            self._finish_failed(job_id, "invalid_generation_request", str(exc), retryable=False)
        except Exception as exc:  # 공급자·런타임 오류는 작업 실패로 보존해야 한다.
            self._finish_failed(job_id, "generation_failed", str(exc), retryable=True)

    def _start(self, job_id: str) -> bool:
        directory = self._directory(job_id)
        with _locked(directory / ".write.lock"):
            state = _read_json(directory / "job.json")
            if state["status"] == GenerationJobStatus.CANCELLED.value:
                return False
            if state["status"] != GenerationJobStatus.QUEUED.value:
                return False
            now = _now()
            state["sequence"] += 1
            state.update(
                {
                    "status": GenerationJobStatus.RUNNING.value,
                    "stage": PipelineStage.VALIDATING_INPUT.value,
                    "message": "생성 작업을 시작했습니다.",
                    "started_at": now,
                    "updated_at": now,
                }
            )
            state["_events"].append(
                self._event(
                    state["sequence"],
                    state["status"],
                    state["stage"],
                    state["message"],
                    completed_assets=0,
                    total_assets=state["total_assets"],
                )
            )
            _replace_json(directory / "job.json", state)
        return True

    def _record_progress(self, job_id: str, progress: PipelineProgress) -> None:
        directory = self._directory(job_id)
        with _locked(directory / ".write.lock"):
            state = _read_json(directory / "job.json")
            if state["status"] in TERMINAL_STATUSES:
                return
            state["sequence"] += 1
            state["stage"] = progress.stage.value
            state["message"] = progress.message
            state["updated_at"] = _now()
            if progress.completed_assets is not None:
                state["completed_assets"] = progress.completed_assets
            if progress.total_assets is not None:
                state["total_assets"] = progress.total_assets
            state["model_calls"] += progress.model_calls_delta
            state["image_generation_calls"] += progress.image_generation_calls_delta
            state["preprocessing_calls"] += progress.preprocessing_calls_delta
            state["recorded_cost_usd"] = round(
                state["recorded_cost_usd"] + progress.recorded_cost_delta_usd,
                6,
            )
            state["_events"].append(
                self._event(
                    state["sequence"],
                    state["status"],
                    state["stage"],
                    state["message"],
                    asset_type=progress.asset_type,
                    completed_assets=state["completed_assets"],
                    total_assets=state["total_assets"],
                )
            )
            _replace_json(directory / "job.json", state)

    def _cancel_requested(self, job_id: str) -> bool:
        return self._state(job_id)["status"] in {
            GenerationJobStatus.CANCEL_REQUESTED.value,
            GenerationJobStatus.CANCELLED.value,
        }

    def _finish_succeeded(self, job_id: str, result: GenerationResult) -> None:
        self._finish(
            job_id,
            status=GenerationJobStatus.SUCCEEDED,
            stage=PipelineStage.COMPLETED,
            message="생성 결과가 준비되었습니다.",
            result_url=f"/v1/generation-jobs/{job_id}/result",
            recorded_cost_usd=result.metrics.estimated_cost_usd,
        )

    def _finish_cancelled(self, job_id: str) -> None:
        self._finish(
            job_id,
            status=GenerationJobStatus.CANCELLED,
            message="안전한 체크포인트에서 생성 작업을 중단했습니다.",
        )

    def _finish_failed(self, job_id: str, code: str, message: str, *, retryable: bool) -> None:
        self._finish(
            job_id,
            status=GenerationJobStatus.FAILED,
            message="생성 작업에 실패했습니다.",
            error={"code": code, "message": message[:1000], "retryable": retryable},
        )

    def _finish(
        self,
        job_id: str,
        *,
        status: GenerationJobStatus,
        message: str,
        stage: PipelineStage | None = None,
        result_url: str | None = None,
        recorded_cost_usd: float | None = None,
        error: dict | None = None,
    ) -> None:
        directory = self._directory(job_id)
        with _locked(directory / ".write.lock"):
            state = _read_json(directory / "job.json")
            if state["status"] in TERMINAL_STATUSES:
                return
            now = _now()
            state["sequence"] += 1
            state.update(
                {
                    "status": status.value,
                    "stage": stage.value if stage is not None else state["stage"],
                    "message": message,
                    "updated_at": now,
                    "finished_at": now,
                    "result_url": result_url,
                    "error": error,
                }
            )
            if recorded_cost_usd is not None:
                state["recorded_cost_usd"] = recorded_cost_usd
            state["_events"].append(
                self._event(
                    state["sequence"],
                    state["status"],
                    state["stage"],
                    state["message"],
                    completed_assets=state["completed_assets"],
                    total_assets=state["total_assets"],
                )
            )
            _replace_json(directory / "job.json", state)

    def _recover_jobs(self) -> None:
        for directory in self.store_root.iterdir():
            if (
                directory.is_symlink()
                or not directory.is_dir()
                or not IDENTIFIER.fullmatch(directory.name)
            ):
                continue
            try:
                state = _read_json(directory / "job.json")
                if state["status"] == GenerationJobStatus.QUEUED.value:
                    self._submit(directory.name)
                elif state["status"] == GenerationJobStatus.CANCEL_REQUESTED.value:
                    self._finish_cancelled(directory.name)
                elif state["status"] == GenerationJobStatus.RUNNING.value:
                    self._finish_failed(
                        directory.name,
                        "worker_restarted",
                        "작업 실행 중 서비스가 다시 시작되었습니다. 새 작업으로 재시도해 주세요.",
                        retryable=True,
                    )
            except GenerationJobError:
                continue
