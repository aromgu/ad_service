"""네이버 커머스 API 클라이언트.

인증 규격 (CLAUDE.md 의 주의사항과 동일):
- 모든 필수 파라미터는 **body** 에 담고 Content-Type 은 x-www-form-urlencoded
- grant_type 은 조건과 무관하게 항상 "client_credentials"
- type 이 SELF 면 account_id 를 **보내지 않는다**. SELLER 면 반드시 보낸다.
- client_secret_sign 은 `{client_id}_{timestamp}` 를 client_secret 을 salt 로
  bcrypt 해시한 뒤 base64 로 인코딩한 값
"""

import base64
import logging
import time
from dataclasses import dataclass

import bcrypt
import httpx

logger = logging.getLogger(__name__)

TOKEN_PATH = "/v1/oauth2/token"
# 토큰 만료 직전에 재발급하지 않도록 여유를 둔다.
EXPIRY_MARGIN_SECONDS = 60
# 상품 목록에 보여 줄 판매 상태. 삭제된 상품만 빼고 모두 보여 준다.
LISTED_STATUS_TYPES = [
    "WAIT", "SALE", "OUTOFSTOCK", "UNADMISSION", "REJECTION", "SUSPENSION", "CLOSE", "PROHIBITION",
]


class NaverApiError(RuntimeError):
    """네이버 API 가 실패를 응답했을 때. 사용자에게 보여줄 메시지를 담는다."""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class _Token:
    value: str
    expires_at: float

    @property
    def alive(self) -> bool:
        return time.time() < self.expires_at - EXPIRY_MARGIN_SECONDS


def make_signature(client_id: str, client_secret: str, timestamp_ms: int) -> str:
    """전자서명 생성. client_secret 이 bcrypt salt 로 쓰인다."""
    password = f"{client_id}_{timestamp_ms}".encode()
    hashed = bcrypt.hashpw(password, client_secret.encode())
    return base64.b64encode(hashed).decode()


class NaverCommerceClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        # 문서의 Base URL 그대로. 경로는 /v1/... 로 쓴다.
        base_url: str = "https://api.commerce.naver.com/external",
        account_type: str = "SELF",
        account_id: str = "",
        timeout: float = 20.0,
    ):
        if not client_id or not client_secret:
            raise NaverApiError(
                "네이버 커머스 API 키가 설정되지 않았습니다. "
                "web/backend/.env 의 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 을 채워 주세요."
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.account_type = account_type.upper()
        self.account_id = account_id
        self.timeout = timeout
        self._token: _Token | None = None

    # ---------- 인증 ----------
    def _token_payload(self) -> dict[str, str]:
        ts = int(time.time() * 1000)
        payload = {
            "client_id": self.client_id,
            "timestamp": str(ts),
            "client_secret_sign": make_signature(self.client_id, self.client_secret, ts),
            "grant_type": "client_credentials",
            "type": self.account_type,
        }
        # SELF 는 account_id 를 넣으면 안 되고, SELLER 는 반드시 넣어야 한다.
        if self.account_type == "SELLER":
            if not self.account_id:
                raise NaverApiError(
                    "type=SELLER 로 설정했으면 NAVER_ACCOUNT_ID(스토어 계정 ID)가 필요합니다."
                )
            payload["account_id"] = self.account_id
        return payload

    def get_token(self, *, force: bool = False) -> str:
        if not force and self._token and self._token.alive:
            return self._token.value

        with httpx.Client(timeout=self.timeout) as c:
            res = c.post(
                f"{self.base_url}{TOKEN_PATH}",
                data=self._token_payload(),  # httpx 가 form-urlencoded 로 보낸다
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if res.status_code != 200:
            raise NaverApiError(
                _explain_token_error(res),
                status=res.status_code,
                body=res.text[:800],
            )

        data = res.json()
        token = data.get("access_token")
        if not token:
            raise NaverApiError("토큰 응답에 access_token 이 없습니다.", body=res.text[:400])
        self._token = _Token(token, time.time() + float(data.get("expires_in", 1800)))
        return token

    # ---------- 공통 호출 ----------
    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.get_token()}",
            "Accept": "application/json",
            **kwargs.pop("headers", {}),
        }
        with httpx.Client(timeout=self.timeout) as c:
            res = c.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)

        # 토큰이 만료됐으면 한 번만 재발급해 재시도한다.
        if res.status_code == 401:
            headers["Authorization"] = f"Bearer {self.get_token(force=True)}"
            with httpx.Client(timeout=self.timeout) as c:
                res = c.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        return res

    # ---------- 읽기 전용 확인 ----------
    def get_channels(self) -> list[dict]:
        """판매자의 채널 목록. 연결 확인용 — 아무것도 바꾸지 않는다."""
        res = self.request("GET", "/v1/seller/channels")
        if res.status_code != 200:
            raise NaverApiError(
                f"채널 조회 실패 ({res.status_code})", status=res.status_code, body=res.text[:800]
            )
        data = res.json()
        return data if isinstance(data, list) else data.get("channels", [])


    # ---------- 메타 조회 ----------
    def get_leaf_categories(self) -> list[dict]:
        """말단 카테고리 전체. 상품 등록에 필요한 leafCategoryId 를 여기서 고른다."""
        res = self.request("GET", "/v1/categories?lastCategory=true")
        self._raise_for(res, "카테고리 조회")
        return [c for c in res.json() if c.get("last")]

    def get_notice_fields(self, notice_type: str) -> list[dict]:
        """상품정보제공고시 상품군의 입력 항목. 필드명·타입·길이를 그대로 준다."""
        res = self.request("GET", f"/v1/products-for-provided-notice/{notice_type}")
        self._raise_for(res, f"고시 항목 조회({notice_type})")
        return res.json().get("productInfoProvidedNoticeContents", [])

    # ---------- 이미지 ----------
    def upload_images(self, files: list[tuple[str, bytes, str]]) -> list[str]:
        """이미지를 네이버에 올리고 호스팅 URL 을 받는다.

        상품 등록의 images URL 은 **반드시 이 API 로 올린 URL** 이어야 한다.
        외부 호스트 직접 링크는 거부된다. 한 번에 최대 10개.
        """
        if not files:
            return []
        multipart = [("imageFiles", (name, data, ctype)) for name, data, ctype in files[:10]]
        res = self.request("POST", "/v1/product-images/upload", files=multipart)
        self._raise_for(res, "이미지 업로드")
        return [img["url"] for img in res.json().get("images", [])]

    # ---------- 상품 ----------
    def register_product(self, payload: dict) -> dict:
        """원상품 + 스마트스토어 채널상품을 한 번에 등록한다."""
        res = self.request(
            "POST", "/v2/products", json=payload, headers={"Content-Type": "application/json"}
        )
        self._raise_for(res, "상품 등록")
        return res.json()

    def get_origin_product(self, origin_product_no: int | str) -> dict:
        """원상품 전체 정보 {originProduct, smartstoreChannelProduct, ...}."""
        res = self.request("GET", f"/v2/products/origin-products/{origin_product_no}")
        self._raise_for(res, "상품 조회")
        return res.json()

    def update_origin_product(self, origin_product_no: int | str, payload: dict) -> dict:
        """원상품 수정. 요청에 빠진 정보는 네이버에서 지워지므로 조회한 전체 정보를 고쳐 보낸다."""
        res = self.request(
            "PUT",
            f"/v2/products/origin-products/{origin_product_no}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        self._raise_for(res, "상품 수정")
        return res.json()

    def delete_origin_product(self, origin_product_no: int | str) -> None:
        res = self.request("DELETE", f"/v2/products/origin-products/{origin_product_no}")
        if res.status_code not in (200, 204):
            self._raise_for(res, "상품 삭제")

    def search_products(self, page: int = 1, size: int = 20) -> dict:
        res = self.request(
            "POST",
            "/v1/products/search",
            json={"page": page, "size": size, "productStatusTypes": LISTED_STATUS_TYPES},
            headers={"Content-Type": "application/json"},
        )
        self._raise_for(res, "상품 목록 조회")
        return res.json()

    @staticmethod
    def _raise_for(res: httpx.Response, what: str) -> None:
        if res.status_code < 300:
            return
        detail = ""
        try:
            body = res.json()
            detail = body.get("message") or ""
            # 검증 오류는 어떤 필드가 문제인지 함께 준다
            for key in ("invalidInputs", "errors", "details"):
                if body.get(key):
                    detail += f" — {body[key]}"
                    break
        except Exception:
            detail = (res.text or "")[:300]
        raise NaverApiError(
            f"{what} 실패 ({res.status_code}) {detail}".strip(),
            status=res.status_code,
            body=(res.text or "")[:2000],
        )


def _explain_token_error(res: httpx.Response) -> str:
    """네이버가 주는 에러를 사람이 고칠 수 있는 문장으로."""
    text = res.text or ""
    if res.status_code == 401:
        return (
            "인증에 실패했습니다. client_id / client_secret 이 맞는지, "
            "애플리케이션이 활성 상태인지 확인해 주세요."
        )
    if "account_id" in text:
        return (
            "account_id 관련 오류입니다. type=SELF 면 account_id 를 빼고, "
            "type=SELLER 면 스토어 계정 ID 를 넣어야 합니다."
        )
    return f"토큰 발급 실패 ({res.status_code})"
