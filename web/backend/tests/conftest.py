import os
import tempfile
from pathlib import Path

import pytest

# 설정 캐시가 만들어지기 전에 테스트용 환경으로 덮어쓴다.
_tmp = tempfile.mkdtemp(prefix="smith-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"
os.environ["MOCK_DURATION_SECONDS"] = "0.5"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ALLOW_DEMO_USER"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def png_bytes() -> bytes:
    """1×1 PNG. 업로드 경로 검증용."""
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


@pytest.fixture
def sample_form() -> dict:
    return {
        "product_name": "시카마누 바이옴 세럼",
        "target": "20-30대 여성",
        "language": "자동",
        "tone": "감성적",
        "length": "숏(10장 내외)",
        "features": "피부 톤 개선, 보습 효과, 저자극 성분",
    }
