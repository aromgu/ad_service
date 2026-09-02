from pathlib import Path

from fastapi.testclient import TestClient

from ad_service.api.main import create_app
from ad_service.api.routes.generate import get_pipeline
from ad_service.core.config import get_settings


def _demo_client(output_root: Path, monkeypatch) -> TestClient:
    """각 테스트가 자신만의 결과 폴더를 사용하도록 앱 설정을 초기화합니다."""

    monkeypatch.setenv("AD_OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("AD_COPY_PROVIDER", "mock")
    monkeypatch.setenv("AD_IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("AD_BACKGROUND_REMOVER", "simple")
    get_settings.cache_clear()
    get_pipeline.cache_clear()
    return TestClient(create_app())


def test_demo_page_is_available(tmp_path, monkeypatch) -> None:
    client = _demo_client(tmp_path / "outputs", monkeypatch)

    response = client.get("/demo")

    assert response.status_code == 200
    assert "광고 생성 모델 실험실" in response.text
    assert 'id="generation-form"' in response.text
    assert "상품 카테고리" in response.text
    assert "판매 채널" in response.text
    assert "광고 목적" in response.text


def test_demo_can_fetch_generated_image(tmp_path, monkeypatch) -> None:
    """화면이 생성 API를 호출한 뒤 결과 이미지를 다시 읽을 수 있어야 합니다."""

    client = _demo_client(tmp_path / "outputs", monkeypatch)
    generation = client.post(
        "/v1/generate",
        json={
            "request_id": "demo_test_001",
            "text": "따뜻한 분위기의 친환경 수제 비누 광고",
            "image_path": None,
            "outputs": ["copy", "banner"],
            "options": {
                "business_type": "food_retail",
                "product_category": "packaged_food",
                "sales_channel": "smart_store",
                "campaign_goal": "product_launch",
                "target_audience": "친환경 제품에 관심 있는 고객",
                "tone": "따뜻하고 자연스러운",
                "price": None,
                "offer": None,
            },
            "source": {"purpose": "test"},
        },
    )
    assert generation.status_code == 200
    result = generation.json()
    filename = Path(result["assets"][0]["path"]).name

    image_response = client.get(f"/v1/results/demo_test_001/{filename}")

    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content.startswith(b"\x89PNG")


def test_result_route_does_not_expose_other_files(tmp_path, monkeypatch) -> None:
    """결과 폴더 밖의 파일을 URL로 읽으려는 요청은 거절해야 합니다."""

    client = _demo_client(tmp_path / "outputs", monkeypatch)

    response = client.get("/v1/results/invalid.id/secret.txt")

    assert response.status_code == 404
