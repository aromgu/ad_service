"""API 전체 흐름 테스트: 접수 → 폴링 → 결과 → 자산."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from ad_service.api.main import create_app
from ad_service.core.config import get_settings


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    # 출력물이 저장소를 오염시키지 않도록 임시 경로로.
    get_settings.cache_clear()
    monkeypatch.setenv("AD_OUTPUT_ROOT", str(tmp_path / "outputs"))
    monkeypatch.setenv("AD_UPLOAD_ROOT", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _wait_for_job(client: TestClient, request_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/v1/jobs/{request_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.1)
    raise AssertionError("job 이 시간 안에 끝나지 않았습니다")


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_generate_copy_and_banner_flow(client: TestClient) -> None:
    payload = {
        "text": "국산 딸기로 만든 300g 수제 딸기잼",
        "outputs": ["copy", "banner"],
        "options": {"store_name": "OO 카페", "tone": "밝고 믿음직한"},
    }
    accepted = client.post("/api/v1/generate", json=payload)
    assert accepted.status_code == 202
    request_id = accepted.json()["request_id"]
    assert accepted.json()["poll_url"] == f"/api/v1/jobs/{request_id}"

    job = _wait_for_job(client, request_id)
    assert job["status"] == "done"

    result = job["result"]
    assert result["mode"] == "text_only"
    assert len(result["copy"]["headline_candidates"]) == 3
    assert len(result["assets"]) == 1

    asset_url = result["assets"][0]["url"]
    assert asset_url.startswith(f"/api/v1/assets/{request_id}/")
    img = client.get(asset_url)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"


def test_validation_error_envelope(client: TestClient) -> None:
    # text 도 image 도 없음
    res = client.post("/api/v1/generate", json={"outputs": ["banner"]})
    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "message" in body["error"]


def test_copy_without_text_rejected(client: TestClient) -> None:
    res = client.post(
        "/api/v1/generate",
        json={"outputs": ["copy"], "options": {"store_name": "x"}},
    )
    assert res.status_code == 422


def test_unknown_job_returns_404(client: TestClient) -> None:
    res = client.get("/api/v1/jobs/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_multipart_with_image(client: TestClient) -> None:
    # 1x1 PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d4944415478da6364f80f00010101000567f3450000000049454e44ae426082"
    )
    res = client.post(
        "/api/v1/generate",
        data={"payload": '{"outputs": ["banner"]}'},
        files={"image": ("p.png", png, "image/png")},
    )
    assert res.status_code == 202
    job = _wait_for_job(client, res.json()["request_id"])
    assert job["status"] == "done"
    assert job["result"]["mode"] == "image_only"
