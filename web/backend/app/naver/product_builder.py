"""ProductDraft → 네이버 상품 등록 페이로드.

이미지 URL 은 반드시 네이버 이미지 업로드 API 로 올린 것이어야 한다.
고시 항목(productInfoProvidedNotice)은 상품군마다 필드가 달라, 값을 짜 넣지 않고
API 로 받은 항목 정의를 그대로 채운다.
"""

from typing import Any

# 택배사 이름 → 네이버 코드
DELIVERY_COMPANY_CODES = {
    "CJ대한통운": "CJGLS",
    "롯데택배": "LOTTE",
    "한진택배": "HANJIN",
    "우체국택배": "EPOST",
    "로젠택배": "LOGEN",
}

# 고시 상품군 → 페이로드에서 쓰는 하위 키 (camelCase)
NOTICE_FIELD_KEY = {
    "COSMETIC": "cosmetic",
    "BAG": "bag",
    "SHOES": "shoes",
    "WEAR": "wear",
    "FASHION_ITEMS": "fashionItems",
    "KITCHEN_UTENSILS": "kitchenUtensils",
    "FURNITURE": "furniture",
    "SLEEPING_GEAR": "sleepingGear",
    "FOOD": "food",
    "DIET_FOOD": "dietFood",
    "BOOKS": "books",
    "SPORTS_EQUIPMENT": "sportsEquipment",
    "MUSICAL_INSTRUMENT": "musicalInstrument",
    "KIDS": "kids",
    "ETC": "etc",
}

DEFAULT_NOTICE_TEXT = "상세 페이지 참조"


def build_notice(notice_type: str, fields: list[dict], *, defaults: dict[str, str] | None = None) -> dict:
    """API 가 알려준 항목 정의대로 고시 정보를 채운다.

    값을 모르는 항목은 '상세 페이지 참조'로 둔다 — 스마트스토어에서 흔히 쓰는 방식이고,
    빈 값으로 두면 등록이 거절된다.
    """
    defaults = defaults or {}
    body: dict[str, Any] = {}
    for f in fields:
        name = f.get("fieldName")
        if not name:
            continue
        if f.get("fieldType") != "String":
            # YearMonth 등은 형식이 엄격해 임의로 채우지 않는다 (대부분 선택 항목).
            continue
        value = defaults.get(name, DEFAULT_NOTICE_TEXT)
        limit = f.get("fieldMaxLength") or 200
        body[name] = value[:limit]

    key = NOTICE_FIELD_KEY.get(notice_type, "etc")
    return {"productInfoProvidedNoticeType": notice_type, key: body}


def build_payload(
    *,
    name: str,
    leaf_category_id: str,
    detail_content_html: str,
    image_urls: list[str],
    sale_price: int,
    stock_quantity: int,
    notice: dict,
    shipping: dict,
    seller_code: str = "",
    brand: str = "",
    manufacturer: str = "",
    tags: list[str] | None = None,
    origin_area_code: str = "00",  # 국산. 수입 코드를 쓰면 importer 가 필수가 된다.
) -> dict:
    if not image_urls:
        raise ValueError("대표 이미지가 필요합니다.")

    courier = shipping.get("courier") or "CJ대한통운"
    shipping_fee = int(shipping.get("shipping_fee") or 0)
    cs_phone = (shipping.get("cs_phone") or "").strip() or "000-0000-0000"

    delivery_fee: dict[str, Any] = (
        {"deliveryFeeType": "FREE"}
        if shipping_fee <= 0
        else {"deliveryFeeType": "PAID", "baseFee": shipping_fee, "deliveryFeePayType": "PREPAID"}
    )

    origin: dict[str, Any] = {
        "statusType": "SALE",
        "saleType": "NEW",
        "leafCategoryId": str(leaf_category_id),
        "name": name[:100],
        "detailContent": detail_content_html,
        "images": {
            "representativeImage": {"url": image_urls[0]},
            "optionalImages": [{"url": u} for u in image_urls[1:10]],
        },
        "salePrice": int(sale_price),
        "stockQuantity": int(stock_quantity),
        "deliveryInfo": {
            "deliveryType": "DELIVERY",
            "deliveryAttributeType": "NORMAL",
            "deliveryCompany": DELIVERY_COMPANY_CODES.get(courier, "CJGLS"),
            "deliveryFee": delivery_fee,
            "claimDeliveryInfo": {
                "returnDeliveryFee": int(shipping.get("return_fee") or 0),
                "exchangeDeliveryFee": int(shipping.get("exchange_fee") or 0),
            },
        },
        "detailAttribute": {
            "afterServiceInfo": {
                "afterServiceTelephoneNumber": cs_phone,
                "afterServiceGuideContent": "상세 페이지의 안내를 참고해 주세요.",
            },
            "originAreaInfo": {"originAreaCode": origin_area_code},
            "productInfoProvidedNotice": notice,
            "taxType": "TAX",
            "minorPurchasable": True,
        },
    }
    if not origin["images"]["optionalImages"]:
        origin["images"].pop("optionalImages")
    if seller_code:
        origin["detailAttribute"]["sellerCodeInfo"] = {"sellerManagementCode": seller_code[:40]}
    if brand or manufacturer:
        origin["detailAttribute"]["naverShoppingSearchInfo"] = {
            k: v for k, v in (("brandName", brand), ("manufacturerName", manufacturer)) if v
        }
    if tags:
        origin["detailAttribute"]["seoInfo"] = {"sellerTags": [{"text": t[:20]} for t in tags[:10]]}

    return {
        "originProduct": origin,
        "smartstoreChannelProduct": {
            "naverShoppingRegistration": False,
            "channelProductDisplayStatusType": "ON",
        },
    }
