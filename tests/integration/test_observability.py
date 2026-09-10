"""/metrics, request_id 헤더, job 메트릭."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from ad_service.api.main import create_app
from ad_service.core.config import get_settings


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    get_settings.cache_clear()
    monkeypatch.setenv("AD_OUTPUT_ROOT", str(tmp_path / "out"))
    monkeypatch.setenv("AD_UPLOAD_ROOT", str(tmp_path / "up"))
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_metrics_endpoint_exposed(client: TestClient) -> None:
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "http_requests_total" in res.text


def test_request_id_header_roundtrip(client: TestClient) -> None:
    res = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert res.headers["X-Request-ID"] == "abc123"

    res2 = client.get("/health")
    assert res2.headers.get("X-Request-ID")  # 자동 생성


def test_job_metrics_increment(client: TestClient) -> None:
    res = client.post("/api/v1/generate", json={"text": "메트릭 테스트", "outputs": ["copy"]})
    request_id = res.json()["request_id"]
    for _ in range(50):
        if client.get(f"/api/v1/jobs/{request_id}").json()["status"] == "done":
            break
        time.sleep(0.1)

    metrics = client.get("/metrics").text
    assert 'ad_jobs_total{status="done"}' in metrics
    assert "ad_job_duration_seconds_count" in metrics
