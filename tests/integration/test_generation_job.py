from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient

from ad_service.api.main import create_app
from ad_service.api.routes import generation_job as generation_job_routes
from ad_service.api.routes.generate import get_pipeline
from ad_service.api.routes.generation_job import get_generation_job_service
from ad_service.core.config import get_settings
from ad_service.core.progress import (
    GenerationCancelledError,
    PipelineProgress,
    PipelineStage,
)
from ad_service.models.image_generator import MockImageProvider
from ad_service.models.vlm import MockCopyProvider
from ad_service.pipelines.generation_job import GenerationJobService
from ad_service.pipelines.inference import GenerationPipeline
from ad_service.pipelines.preprocessing import SimpleBackgroundRemover


def _body(request_id: str, outputs=None) -> dict:
    return {
        "request": {
            "request_id": request_id,
            "text": "도소매 판매자를 위한 테스트 상품",
            "image_path": None,
            "outputs": outputs or ["copy", "banner"],
            "options": {},
            "source": {"purpose": "generation job integration test"},
        },
        "seed": 0,
    }


def _wait(client: TestClient, job_id: str, statuses=None, timeout: float = 5.0) -> dict:
    expected = statuses or {"succeeded", "failed", "cancelled"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/generation-jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in expected:
            return body
        time.sleep(0.01)
    raise AssertionError(f"작업이 제한 시간 안에 완료되지 않았습니다: {job_id}")


def _mock_client(tmp_path, monkeypatch):
    output_root = tmp_path / "outputs"
    monkeypatch.setenv("AD_OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("AD_COPY_PROVIDER", "mock")
    monkeypatch.setenv("AD_IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("AD_BACKGROUND_REMOVER", "simple")
    get_settings.cache_clear()
    get_pipeline.cache_clear()
    get_generation_job_service.cache_clear()
    return TestClient(create_app()), output_root


def test_success_exposes_real_stages_without_fake_percent(tmp_path, monkeypatch) -> None:
    client, output_root = _mock_client(tmp_path, monkeypatch)

    created = client.post("/v1/generation-jobs", json=_body("job_success_001"))

    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    completed = _wait(client, "job_success_001")
    assert completed["status"] == "succeeded"
    assert completed["stage"] == "completed"
    assert completed["progress_percent"] is None
    assert completed["estimated_remaining_ms"] is None
    assert completed["model_calls"] == 2
    assert completed["image_generation_calls"] == 1
    assert completed["preprocessing_calls"] == 0
    assert completed["completed_assets"] == completed["total_assets"] == 1
    assert completed["result_url"] == "/v1/generation-jobs/job_success_001/result"
    assert completed["can_cancel"] is False
    assert completed["can_retry"] is False

    events_response = client.get("/v1/generation-jobs/job_success_001/events")
    assert events_response.status_code == 200
    events = events_response.json()["items"]
    sequences = [event["sequence"] for event in events]
    assert sequences == list(range(1, len(events) + 1))
    assert all(event["progress_percent"] is None for event in events)
    stages = {event["stage"] for event in events}
    assert {
        "queued",
        "validating_input",
        "generating_copy",
        "generating_images",
        "compositing",
        "validating_result",
        "completed",
    } <= stages

    tail = client.get(
        "/v1/generation-jobs/job_success_001/events",
        params={"after_sequence": sequences[-2]},
    ).json()
    assert [event["sequence"] for event in tail["items"]] == [sequences[-1]]
    assert client.get(completed["result_url"]).status_code == 200
    assert (output_root / "job_success_001" / "result.json").is_file()

    replay = client.post("/v1/generation-jobs", json=_body("job_success_001"))
    assert replay.status_code == 202
    assert replay.json()["replayed"] is True
    conflict = _body("job_success_001", outputs=["copy"])
    assert client.post("/v1/generation-jobs", json=conflict).status_code == 409

    get_generation_job_service().shutdown()
    get_generation_job_service.cache_clear()


class BlockingPipeline:
    def __init__(self, started: Event, release: Event) -> None:
        self.started = started
        self.release = release

    def generate(
        self,
        request,
        seed,
        base_dir,
        *,
        progress_callback,
        cancellation_check,
    ):
        del request, seed, base_dir
        progress_callback(
            PipelineProgress(
                PipelineStage.GENERATING_IMAGES,
                "테스트 이미지 모델을 호출했습니다.",
                model_calls_delta=1,
                image_generation_calls_delta=1,
            )
        )
        self.started.set()
        if not self.release.wait(timeout=3):
            raise RuntimeError("테스트 호출 해제 시간이 초과되었습니다")
        progress_callback(
            PipelineProgress(
                PipelineStage.GENERATING_IMAGES,
                "테스트 이미지 모델 호출이 끝났습니다.",
                recorded_cost_delta_usd=0.012,
            )
        )
        if cancellation_check():
            raise GenerationCancelledError("취소됨")
        raise RuntimeError("테스트 작업 종료")


def _custom_client(service: GenerationJobService, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        generation_job_routes,
        "get_generation_job_service",
        lambda: service,
    )
    return TestClient(create_app())


def test_queued_cancel_stops_before_any_model_call(tmp_path, monkeypatch) -> None:
    started = Event()
    release = Event()
    blocking = BlockingPipeline(started, release)
    service = GenerationJobService(tmp_path / "outputs", lambda: blocking)
    client = _custom_client(service, monkeypatch)

    client.post("/v1/generation-jobs", json=_body("blocking_job", outputs=["banner"]))
    assert started.wait(timeout=2)
    queued = client.post(
        "/v1/generation-jobs",
        json=_body("queued_cancel_job", outputs=["banner"]),
    )
    assert queued.status_code == 202

    cancelled = client.post("/v1/generation-jobs/queued_cancel_job/cancel")

    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["model_calls"] == 0
    assert body["image_generation_calls"] == 0
    assert body["recorded_cost_usd"] == 0
    assert body["can_retry"] is True
    assert client.post("/v1/generation-jobs/queued_cancel_job/cancel").json()["replayed"] is True

    client.post("/v1/generation-jobs/blocking_job/cancel")
    release.set()
    assert _wait(client, "blocking_job")["status"] == "cancelled"
    service.shutdown()


def test_running_cancel_waits_for_checkpoint_and_keeps_recorded_cost(tmp_path, monkeypatch) -> None:
    started = Event()
    release = Event()
    service = GenerationJobService(
        tmp_path / "outputs",
        lambda: BlockingPipeline(started, release),
    )
    client = _custom_client(service, monkeypatch)
    client.post("/v1/generation-jobs", json=_body("running_cancel_job", outputs=["banner"]))
    assert started.wait(timeout=2)

    requested = client.post("/v1/generation-jobs/running_cancel_job/cancel")

    assert requested.status_code == 200
    assert requested.json()["status"] == "cancel_requested"
    assert requested.json()["finished_at"] is None
    release.set()
    cancelled = _wait(client, "running_cancel_job")
    assert cancelled["status"] == "cancelled"
    assert cancelled["model_calls"] == 1
    assert cancelled["image_generation_calls"] == 1
    assert cancelled["recorded_cost_usd"] == 0.012
    statuses = [
        item["status"]
        for item in client.get("/v1/generation-jobs/running_cancel_job/events").json()["items"]
    ]
    assert "cancel_requested" in statuses
    assert statuses[-1] == "cancelled"
    service.shutdown()


class FailFirstPipeline:
    def __init__(self, output_root: Path) -> None:
        self.real = GenerationPipeline(
            copy_provider=MockCopyProvider(),
            image_provider=MockImageProvider(),
            background_remover=SimpleBackgroundRemover(),
            output_root=output_root,
        )

    def generate(self, request, seed, base_dir, **kwargs):
        if request.request_id == "failed_job":
            kwargs["progress_callback"](
                PipelineProgress(
                    PipelineStage.GENERATING_COPY,
                    "실패 테스트 모델을 호출했습니다.",
                    model_calls_delta=1,
                )
            )
            raise RuntimeError("일시적인 공급자 오류")
        return self.real.generate(request, seed, base_dir, **kwargs)


def test_failed_job_retries_as_new_immutable_job(tmp_path, monkeypatch) -> None:
    output_root = tmp_path / "outputs"
    pipeline = FailFirstPipeline(output_root)
    service = GenerationJobService(output_root, lambda: pipeline)
    client = _custom_client(service, monkeypatch)

    client.post("/v1/generation-jobs", json=_body("failed_job", outputs=["copy"]))
    failed = _wait(client, "failed_job")
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "generation_failed"
    assert failed["error"]["retryable"] is True
    assert failed["can_retry"] is True

    retried_response = client.post(
        "/v1/generation-jobs/failed_job/retry",
        json={"new_request_id": "retried_job"},
    )

    assert retried_response.status_code == 202
    assert retried_response.json()["retry_of"] == "failed_job"
    assert retried_response.json()["attempt"] == 2
    retried = _wait(client, "retried_job")
    assert retried["status"] == "succeeded"
    assert retried["job_id"] == "retried_job"
    assert client.get("/v1/generation-jobs/failed_job").json()["status"] == "failed"
    assert not (output_root / "failed_job" / "result.json").exists()
    assert (output_root / "retried_job" / "result.json").is_file()
    assert (
        client.post(
            "/v1/generation-jobs/retried_job/retry",
            json={"new_request_id": "invalid_retry"},
        ).status_code
        == 409
    )
    service.shutdown()


def test_missing_jobs_and_invalid_event_cursor_fail_closed(tmp_path, monkeypatch) -> None:
    client, _ = _mock_client(tmp_path, monkeypatch)
    assert client.get("/v1/generation-jobs/missing").status_code == 404
    assert (
        client.get(
            "/v1/generation-jobs/missing/events",
            params={"after_sequence": -1},
        ).status_code
        == 422
    )
    get_generation_job_service().shutdown()
    get_generation_job_service.cache_clear()
