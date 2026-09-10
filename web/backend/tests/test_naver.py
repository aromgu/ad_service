"""네이버 커머스 연동의 순수 로직 테스트.

네트워크를 타지 않는 부분만 다룬다. 실제 호출은 키가 있는 환경에서
scripts 로 확인한다.
"""

import base64

import bcrypt
import pytest

from app.naver import catalog
from app.naver.client import NaverApiError, NaverCommerceClient, make_signature
from app.naver.product_builder import build_notice, build_payload

CLIENT_ID = "test-client-id"
# client_secret 은 bcrypt salt 형식이어야 한다 (커머스API센터가 그렇게 발급한다).
CLIENT_SECRET = bcrypt.gensalt(rounds=4).decode()


# ---------------- 전자서명 ----------------
def test_signature_is_bcrypt_of_id_and_timestamp():
    ts = 1700000000000
    sign = make_signature(CLIENT_ID, CLIENT_SECRET, ts)
    expected = base64.b64encode(
        bcrypt.hashpw(f"{CLIENT_ID}_{ts}".encode(), CLIENT_SECRET.encode())
    ).decode()
    assert sign == expected


def test_signature_changes_with_timestamp():
    a = make_signature(CLIENT_ID, CLIENT_SECRET, 1700000000000)
    b = make_signature(CLIENT_ID, CLIENT_SECRET, 1700000000001)
    assert a != b


# ---------------- 토큰 요청 파라미터 (CLAUDE.md 규칙) ----------------
def _client(**kw) -> NaverCommerceClient:
    return NaverCommerceClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, **kw)


def test_grant_type_is_always_included():
    for kw in ({"account_type": "SELF"}, {"account_type": "SELLER", "account_id": "store-1"}):
        assert _client(**kw)._token_payload()["grant_type"] == "client_credentials"


def test_self_must_not_send_account_id():
    payload = _client(account_type="SELF", account_id="무시되어야-함")._token_payload()
    assert "account_id" not in payload
    assert payload["type"] == "SELF"


def test_seller_must_send_account_id():
    payload = _client(account_type="SELLER", account_id="store-1")._token_payload()
    assert payload["account_id"] == "store-1"
    assert payload["type"] == "SELLER"


def test_seller_without_account_id_is_rejected_early():
    with pytest.raises(NaverApiError, match="NAVER_ACCOUNT_ID"):
        _client(account_type="SELLER")._token_payload()


def test_missing_keys_gives_actionable_message():
    with pytest.raises(NaverApiError, match="NAVER_CLIENT_ID"):
        NaverCommerceClient(client_id="", client_secret="")


# ---------------- 상품정보제공고시 ----------------
COSMETIC_FIELDS = [
    {"fieldType": "String", "fieldName": "capacity", "fieldMaxLength": 200},
    {"fieldType": "String", "fieldName": "manufacturer", "fieldMaxLength": 5},
    {"fieldType": "YearMonth", "fieldName": "expirationDate", "fieldMaxLength": 300},
]


def test_notice_fills_string_fields_only():
    notice = build_notice("COSMETIC", COSMETIC_FIELDS)
    assert notice["productInfoProvidedNoticeType"] == "COSMETIC"
    body = notice["cosmetic"]
    assert body["capacity"] == "상세 페이지 참조"
    # 형식이 엄격한 타입은 임의로 채우지 않는다
    assert "expirationDate" not in body


def test_notice_respects_max_length():
    notice = build_notice("COSMETIC", COSMETIC_FIELDS, defaults={"manufacturer": "아주아주긴제조사이름"})
    assert notice["cosmetic"]["manufacturer"] == "아주아주긴"  # 5자로 잘림


def test_notice_type_is_derived_from_category_path():
    assert catalog.notice_type_for("화장품/미용 › 스킨케어 › 에센스/세럼/앰플") == "COSMETIC"
    assert catalog.notice_type_for("패션잡화 › 여성가방 › 에코백") == "BAG"
    assert catalog.notice_type_for("디지털/가전 › 알 수 없는 것") == "ETC"


# ---------------- 등록 페이로드 ----------------
BASE = dict(
    name="테스트 상품",
    leaf_category_id="50000439",
    detail_content_html="<p>설명</p>",
    image_urls=["https://shop-phinf.pstatic.net/a.jpg", "https://shop-phinf.pstatic.net/b.jpg"],
    sale_price=19900,
    stock_quantity=5,
    notice=build_notice("COSMETIC", COSMETIC_FIELDS),
    shipping={"courier": "롯데택배", "shipping_fee": 3000, "return_fee": 3000,
              "exchange_fee": 6000, "cs_phone": "010-0000-0000"},
)


def test_payload_has_required_fields():
    p = build_payload(**BASE)
    origin = p["originProduct"]
    # 등록 시 statusType 은 SALE 만 허용된다
    assert origin["statusType"] == "SALE"
    assert origin["leafCategoryId"] == "50000439"
    assert origin["salePrice"] == 19900
    assert origin["stockQuantity"] == 5
    assert origin["images"]["representativeImage"]["url"] == BASE["image_urls"][0]
    assert origin["images"]["optionalImages"] == [{"url": BASE["image_urls"][1]}]
    assert p["smartstoreChannelProduct"]["channelProductDisplayStatusType"] == "ON"


def test_payload_uses_domestic_origin_code():
    """수입 코드를 쓰면 importer 가 필수가 되어 등록이 거절된다."""
    assert build_payload(**BASE)["originProduct"]["detailAttribute"]["originAreaInfo"][
        "originAreaCode"
    ] == "00"


def test_courier_name_maps_to_naver_code():
    assert build_payload(**BASE)["originProduct"]["deliveryInfo"]["deliveryCompany"] == "LOTTE"


def test_free_shipping_when_fee_is_zero():
    p = build_payload(**{**BASE, "shipping": {**BASE["shipping"], "shipping_fee": 0}})
    assert p["originProduct"]["deliveryInfo"]["deliveryFee"] == {"deliveryFeeType": "FREE"}


def test_paid_shipping_carries_base_fee():
    fee = build_payload(**BASE)["originProduct"]["deliveryInfo"]["deliveryFee"]
    assert fee["deliveryFeeType"] == "PAID" and fee["baseFee"] == 3000


def test_single_image_omits_optional_images():
    p = build_payload(**{**BASE, "image_urls": ["https://shop-phinf.pstatic.net/only.jpg"]})
    assert "optionalImages" not in p["originProduct"]["images"]


def test_payload_requires_an_image():
    with pytest.raises(ValueError, match="대표 이미지"):
        build_payload(**{**BASE, "image_urls": []})


def test_tags_go_into_seo_info():
    p = build_payload(**BASE, tags=["보습", "저자극"])
    assert p["originProduct"]["detailAttribute"]["seoInfo"]["sellerTags"] == [
        {"text": "보습"}, {"text": "저자극"}
    ]


def test_no_tags_means_no_seo_info():
    assert "seoInfo" not in build_payload(**BASE)["originProduct"]["detailAttribute"]
