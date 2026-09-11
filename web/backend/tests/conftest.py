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
# 테스트는 네이버 API 를 절대 호출하지 않는다. 키를 비워 두면 실수로 부르더라도 곧바로 실패한다.
# 등록 성공 경로는 테스트에서 get_client 를 가짜 클라이언트로 바꿔 확인한다.
os.environ["NAVER_CLIENT_ID"] = ""
os.environ["NAVER_CLIENT_SECRET"] = ""

import copy  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.naver.client import NaverApiError  # noqa: E402


class FakeNaverClient:
    """네이버 대신 쓰는 가짜 클라이언트. 테스트가 실제 스마트스토어를 건드리면 안 된다.

    필요한 응답만 속성으로 바꿔 끼우고, 수정·삭제 요청은 기록해 둔다.
    """

    def __init__(self):
        self.register_result: dict = {"originProductNo": 123, "smartstoreChannelProductNo": 456}
        self.register_error: Exception | None = None
        self.search_result: dict = {"contents": [], "page": 1, "totalElements": 0, "totalPages": 0}
        # originProductNo → 원상품 조회 응답
        self.products: dict[str, dict] = {}
        self.updated: list[tuple[str, dict]] = []
        self.deleted: list[str] = []

    def upload_images(self, files):
        return [f"https://shop-phinf.pstatic.net/fake/{name}" for name, _, _ in files]

    def get_notice_fields(self, notice_type):
        return []

    def get_leaf_categories(self):
        return [{"id": "50000439", "name": "에센스/세럼/앰플", "last": True,
                 "wholeCategoryName": "화장품/미용>스킨케어>에센스/세럼/앰플"}]

    def register_product(self, payload):
        if self.register_error:
            raise self.register_error
        return self.register_result

    def search_products(self, page=1, size=20):
        return self.search_result

    def get_origin_product(self, origin_product_no):
        no = str(origin_product_no)
        if no not in self.products:
            raise NaverApiError("상품 조회 실패 (404) 존재하지 않는 상품입니다.", status=404)
        return copy.deepcopy(self.products[no])

    def update_origin_product(self, origin_product_no, payload):
        self.updated.append((str(origin_product_no), payload))
        return {"originProductNo": int(origin_product_no)}

    def delete_origin_product(self, origin_product_no):
        no = str(origin_product_no)
        if self.products.pop(no, None) is None:
            raise NaverApiError("상품 삭제 실패 (404) 존재하지 않는 상품입니다.", status=404)
        self.deleted.append(no)


@pytest.fixture
def fake_naver(monkeypatch) -> FakeNaverClient:
    """app.naver.service 가 쓰는 클라이언트를 가짜로 바꾼다."""
    from app.naver import service

    fake = FakeNaverClient()
    monkeypatch.setattr(service, "get_client", lambda: fake)
    return fake


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
