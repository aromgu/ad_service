from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from ad_service.api.main import create_app
from ad_service.api.routes.generate import get_pipeline
from ad_service.core.config import get_settings


def test_health_endpoint() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_generate_endpoint_returns_public_copy_field(tmp_path, monkeypatch) -> None:
    source = tmp_path / "product.jpg"
    image = Image.new("RGB", (240, 240), "white")
    ImageDraw.Draw(image).rectangle((70, 30, 170, 220), fill=(80, 40, 160))
    image.save(source)
    monkeypatch.setenv("AD_OUTPUT_ROOT", str(tmp_path / "api_outputs"))
    get_settings.cache_clear()
    get_pipeline.cache_clear()
    response = TestClient(create_app()).post(
        "/v1/generate",
        json={
            "request_id": "api_001",
            "product_name": "테스트 상품",
            "category": "식품/과자",
            "features": ["바삭한 식감"],
            "target_audience": "간식을 찾는 소비자",
            "tone": "밝고 친근함",
            "price": None,
            "offer": None,
            "product_image_path": str(source),
            "product_bbox": {"xmin": 70, "ymin": 30, "xmax": 170, "ymax": 220},
            "source": {},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "copy" in payload
    assert "copy_result" not in payload
    assert len(payload["assets"]) == 3
