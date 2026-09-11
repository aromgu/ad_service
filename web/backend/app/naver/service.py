"""ProductDraft 와 네이버 스마트스토어 상품을 잇는다 — 등록·목록·불러오기·수정·삭제."""

import html
import logging
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from app.core.config import SHARED_IMAGE_DIR, settings
from app.core.korean import eul_reul
from app.db.models import ProductDraft
from app.naver import catalog
from app.naver.client import NaverApiError, NaverCommerceClient
from app.naver.product_builder import build_notice, build_payload

logger = logging.getLogger(__name__)

_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}
# 원상품 조회 응답 중 수정 요청에 다시 실어 보낼 부분. 빠지면 네이버에서 지워진다.
_PRODUCT_PARTS = ("originProduct", "smartstoreChannelProduct", "windowChannelProduct")

_TAG = re.compile(r"<[^>]+>")
_BLOCK_END = re.compile(r"<\s*(?:br\s*/?|/p|/div|/li|/h[1-6])\s*>", re.IGNORECASE)


class MissingFieldsError(NaverApiError):
    """등록 전 필수 입력이 빠졌을 때. 네이버를 호출하기 전에 걸러낸다."""


class WrongStateError(NaverApiError):
    """등록 상태와 맞지 않는 요청 — 등록된 상품을 또 등록하거나, 등록 안 된 상품을 수정·삭제할 때."""


@lru_cache
def get_client() -> NaverCommerceClient:
    return NaverCommerceClient(
        client_id=settings.naver_client_id,
        client_secret=settings.naver_client_secret,
        base_url=settings.naver_api_base,
        account_type=settings.naver_account_type,
        account_id=settings.naver_account_id,
    )


def _local_path(url: str) -> Path | None:
    """우리가 서빙하는 /static/... URL 을 실제 파일 경로로."""
    if url.startswith("/static/uploads/"):
        return settings.upload_path / url.rsplit("/", 1)[-1]
    if url.startswith("/static/images/"):
        return SHARED_IMAGE_DIR / url.rsplit("/", 1)[-1]
    return None


def _detail_html(draft: ProductDraft) -> str:
    """상세페이지 HTML. 네이버는 이미지도 자기 URL 만 받으므로 설명 위주로 구성한다."""
    body = (draft.description or "").strip() or draft.product_name
    paragraphs = "".join(f"<p>{line}</p>" for line in body.splitlines() if line.strip())
    return f"<div>{paragraphs or f'<p>{draft.product_name}</p>'}</div>"


def _html_to_text(markup: str) -> str:
    """상세 HTML 에서 글만 뽑는다. 검토 화면의 '상품 설명' 칸에 보여 줄 용도."""
    text = html.unescape(_TAG.sub("", _BLOCK_END.sub("\n", markup)))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _shipping_fee_of(fee: dict) -> int:
    return 0 if fee.get("deliveryFeeType") == "FREE" else int(fee.get("baseFee") or 0)


def validate(draft: ProductDraft) -> None:
    """네이버가 반드시 요구하는 값이 있는지 본다. 등록과 수정이 같이 쓴다."""
    missing: list[str] = []
    if not (draft.product_name or "").strip():
        missing.append("상품명")
    # 경로만 있고 ID 가 없으면 등록할 수 없다 — 카테고리 검색에서 골라야 ID 가 함께 저장된다.
    if not (draft.selected_category or "").strip() or not (draft.selected_category_id or "").strip():
        missing.append("카테고리")
    if draft.price is None or draft.price <= 0:
        missing.append("판매가")
    if missing:
        # 마지막 항목에만 조사를 붙인다. "상품명, 판매가를 먼저 입력해 주세요."
        listed = ", ".join(missing[:-1] + [eul_reul(missing[-1])])
        raise MissingFieldsError(f"{listed} 먼저 입력해 주세요.")


# ---------------- 이미지 ----------------
def _ordered_images(draft: ProductDraft) -> list[str]:
    """대표 이미지를 맨 앞에 둔다. 네이버는 첫 장을 대표 이미지로 쓴다."""
    urls = list(draft.image_urls or [])
    rep = draft.representative_image_url
    if rep and rep in urls:
        urls.remove(rep)
        urls.insert(0, rep)
    return urls[:10]


def _naver_image_urls(client: NaverCommerceClient, urls: list[str]) -> list[str]:
    """이미지를 네이버가 받는 URL 로 바꾼다. 순서는 그대로 둔다.

    우리 서버 파일(/static/...)은 네이버 이미지 API 로 올리고, 이미 네이버에 올라가 있는
    이미지(스마트스토어에서 불러온 상품)는 그대로 쓴다. 외부 URL 직접 입력은 거부된다.
    """
    out: list[str | None] = []
    local: list[tuple[int, Path]] = []
    for url in urls[:10]:
        path = _local_path(url)
        if path is None:
            if url.startswith("https://"):
                out.append(url)
        elif path.is_file():
            local.append((len(out), path))
            out.append(None)
    if local:
        uploaded = client.upload_images(
            [(p.name, p.read_bytes(), _CONTENT_TYPES.get(p.suffix.lower(), "image/jpeg")) for _, p in local]
        )
        for (i, _), url in zip(local, uploaded):
            out[i] = url
    result = [u for u in out if u]
    if not result:
        raise NaverApiError("등록할 상품 이미지를 찾을 수 없습니다.")
    return result


def _send_with_tag_retry(send: Callable[[dict], dict], payload: dict) -> dict:
    """검색 태그는 상품명·카테고리와 겹치면 거부된다. 그때만 태그를 빼고 한 번 더 보낸다."""
    try:
        return send(payload)
    except NaverApiError as e:
        if not (e.status == 400 and "sellerTags" in (e.body or "")):
            raise
        logger.info("검색 태그가 거부되어 태그 없이 재시도합니다")
        attr = payload["originProduct"].get("detailAttribute") or {}
        seo = attr.get("seoInfo") or {}
        seo.pop("sellerTags", None)
        if not seo:
            attr.pop("seoInfo", None)
        return send(payload)


# ---------------- 등록 ----------------
def register(draft: ProductDraft) -> dict:
    """스마트스토어에 실제로 등록하고 {originProductNo, smartstoreChannelProductNo} 를 돌려준다.

    실패는 NaverApiError 로 올려 보내 라우터가 사용자에게 그대로 보여준다.
    상품번호를 받지 못했다면 등록된 게 아니므로 이것도 실패로 본다.
    """
    if draft.naver_origin_product_no:
        # 다시 등록하면 같은 상품이 스토어에 하나 더 생긴다.
        raise WrongStateError("이미 스마트스토어에 등록된 상품입니다. 고친 내용은 '수정'으로 반영해 주세요.")
    validate(draft)
    client = get_client()

    # 1) 이미지를 네이버로 옮긴다.
    image_urls = _naver_image_urls(client, _ordered_images(draft))

    # 2) 고시 항목은 상품군마다 달라 API 정의를 그대로 채운다.
    notice_type = catalog.notice_type_for(draft.selected_category)
    notice = build_notice(
        notice_type,
        client.get_notice_fields(notice_type),
        defaults={"manufacturer": draft.manufacturer, "producer": draft.manufacturer},
    )

    payload = build_payload(
        name=draft.product_name,
        leaf_category_id=draft.selected_category_id,
        detail_content_html=_detail_html(draft),
        image_urls=image_urls,
        sale_price=int(draft.price or 0),
        stock_quantity=int(draft.stock or 0),
        notice=notice,
        # 검토 화면에서 고친 배송비가 배송 설정 기본값보다 우선한다.
        shipping={**(draft.shipping or {}), "shipping_fee": draft.shipping_fee},
        seller_code=draft.seller_code,
        brand=draft.brand,
        manufacturer=draft.manufacturer,
        tags=list(draft.tags or []),
    )

    result = _send_with_tag_retry(client.register_product, payload)
    if not result.get("originProductNo"):
        raise NaverApiError(
            "네이버가 상품번호를 돌려주지 않아 등록을 확인할 수 없습니다.", body=str(result)[:800]
        )
    return result


# ---------------- 등록된 상품 관리 ----------------
def list_store_products(*, page: int, size: int) -> dict:
    """스마트스토어 상품 목록을 화면에 필요한 만큼만 펼친다."""
    data = get_client().search_products(page=page, size=size)
    items = []
    for content in data.get("contents") or []:
        channels = content.get("channelProducts") or [{}]
        # 스마트스토어 채널을 우선 쓰고, 없으면 첫 채널을 쓴다.
        ch = next((c for c in channels if c.get("channelServiceType") == "STOREFARM"), channels[0])
        items.append(
            {
                "origin_product_no": str(content.get("originProductNo") or ch.get("originProductNo") or ""),
                "channel_product_no": str(ch.get("channelProductNo") or ""),
                "name": ch.get("name") or "",
                "status_type": ch.get("statusType") or "",
                "sale_price": ch.get("salePrice"),
                "stock_quantity": ch.get("stockQuantity"),
                "image_url": (ch.get("representativeImage") or {}).get("url"),
                "category_name": (ch.get("wholeCategoryName") or "").replace(">", " › "),
                "registered_at": ch.get("regDate"),
                "modified_at": ch.get("modifiedDate"),
            }
        )
    return {
        "items": items,
        "page": data.get("page") or page,
        "total": data.get("totalElements") or 0,
        "total_pages": data.get("totalPages") or 0,
    }


def fetch_origin(client: NaverCommerceClient, origin_product_no: str) -> dict:
    """원상품 전체 정보. 없는 상품이면 사용자가 알아볼 수 있는 문장으로 바꾼다."""
    try:
        detail = client.get_origin_product(origin_product_no)
    except NaverApiError as e:
        if e.status == 404:
            raise NaverApiError(
                "스마트스토어에서 찾을 수 없는 상품입니다. 이미 삭제되었을 수 있어요.", status=404
            ) from e
        raise
    if not detail.get("originProduct"):
        raise NaverApiError("네이버 상품 정보가 비어 있습니다.", body=str(detail)[:800])
    return detail


def sync_from_naver(
    draft: ProductDraft, detail: dict, *, origin_product_no: str, category_path: str
) -> None:
    """네이버의 현재 상품 정보로 초안을 맞춘다.

    판매자센터에서 고친 내용이 있을 수 있어 열 때마다 맞춘다.
    검토 화면 전용 값(카드 이름·옵션·KC·속성)은 건드리지 않는다.
    """
    origin = detail.get("originProduct") or {}
    channel = detail.get("smartstoreChannelProduct") or {}
    attr = origin.get("detailAttribute") or {}
    images = origin.get("images") or {}
    urls = [
        u
        for u in [(images.get("representativeImage") or {}).get("url")]
        + [(i or {}).get("url") for i in images.get("optionalImages") or []]
        if u
    ]
    search_info = attr.get("naverShoppingSearchInfo") or {}
    leaf_id = str(origin.get("leafCategoryId") or "")
    description = _html_to_text(origin.get("detailContent") or "")

    draft.status = "registered"
    draft.naver_origin_product_no = str(origin_product_no)
    draft.naver_channel_product_no = str(
        channel.get("channelProductNo") or draft.naver_channel_product_no or ""
    )
    draft.product_name = (origin.get("name") or "")[:200]
    draft.title = draft.title or draft.product_name or "스마트스토어 상품"
    draft.description = description
    analysis = {"source": "스마트스토어에서 불러옴", **(draft.analysis or {})}
    analysis.pop("register_error", None)
    # 수정할 때 설명을 안 고쳤으면 스토어의 상세 HTML 을 그대로 두기 위한 기준값.
    analysis["naver_description"] = description
    draft.analysis = analysis
    draft.image_urls = urls
    draft.representative_image_url = urls[0] if urls else None
    draft.brand = search_info.get("brandName") or ""
    draft.manufacturer = search_info.get("manufacturerName") or ""
    draft.seller_code = (attr.get("sellerCodeInfo") or {}).get("sellerManagementCode") or ""
    draft.selected_category_id = leaf_id
    draft.selected_category = category_path
    draft.category_candidates = (
        [{"id": leaf_id, "path": category_path, "confidence": 0}] if leaf_id else []
    )
    draft.price = origin.get("salePrice")
    draft.stock = int(origin.get("stockQuantity") or 0)
    draft.shipping_fee = _shipping_fee_of((origin.get("deliveryInfo") or {}).get("deliveryFee") or {})
    draft.tags = [
        t["text"] for t in (attr.get("seoInfo") or {}).get("sellerTags") or [] if t.get("text")
    ]
    # 새로 만든 초안이면 검토 화면이 기대하는 기본값을 채운다.
    if draft.options is None:
        draft.options = []
    if not draft.kc:
        draft.kc = {"mode": "none", "detail": "KC 대상 아님", "cert_number": ""}
    if draft.attributes is None:
        draft.attributes = {}
    if draft.shipping is None:
        draft.shipping = {}


def apply_to_origin(origin: dict, draft: ProductDraft, image_urls: list[str]) -> None:
    """조회한 원상품에 검토 화면이 다루는 값만 덮어쓴다. 고시·A/S·옵션 등 나머지는 그대로 둔다."""
    origin["name"] = draft.product_name[:100]
    origin["leafCategoryId"] = str(draft.selected_category_id)
    origin["salePrice"] = int(draft.price or 0)
    origin["stockQuantity"] = int(draft.stock or 0)
    # 품절 상태에서 재고를 채웠으면 다시 판매중으로 돌린다.
    if origin.get("statusType") == "OUTOFSTOCK" and origin["stockQuantity"] > 0:
        origin["statusType"] = "SALE"

    origin["images"] = {"representativeImage": {"url": image_urls[0]}}
    if image_urls[1:]:
        origin["images"]["optionalImages"] = [{"url": u} for u in image_urls[1:10]]

    # 설명을 고치지 않았으면 스토어의 상세 HTML(판매자센터에서 넣은 이미지 등)을 그대로 둔다.
    if (draft.analysis or {}).get("naver_description") != draft.description:
        origin["detailContent"] = _detail_html(draft)

    attr = origin.setdefault("detailAttribute", {})

    search_info = dict(attr.get("naverShoppingSearchInfo") or {})
    for name_key, id_key, value in (
        ("brandName", "brandId", draft.brand),
        ("manufacturerName", "manufacturerId", draft.manufacturer),
    ):
        if (search_info.get(name_key) or "") == value:
            continue
        # 이름을 바꾸면 네이버에 등록된 브랜드/제조사 ID 와 어긋나므로 ID 는 뺀다.
        search_info.pop(id_key, None)
        if value:
            search_info[name_key] = value
        else:
            search_info.pop(name_key, None)
    if search_info:
        attr["naverShoppingSearchInfo"] = search_info
    else:
        attr.pop("naverShoppingSearchInfo", None)

    if draft.seller_code:
        attr["sellerCodeInfo"] = {
            **(attr.get("sellerCodeInfo") or {}),
            "sellerManagementCode": draft.seller_code[:40],
        }

    seo = dict(attr.get("seoInfo") or {})
    if draft.tags:
        seo["sellerTags"] = [{"text": t[:20]} for t in draft.tags[:10]]
    else:
        seo.pop("sellerTags", None)
    if seo:
        attr["seoInfo"] = seo
    else:
        attr.pop("seoInfo", None)

    delivery = origin.get("deliveryInfo")
    if delivery is not None:
        fee = delivery.get("deliveryFee") or {}
        # 배송비를 안 바꿨으면 조건부 무료 같은 기존 설정을 그대로 둔다.
        if _shipping_fee_of(fee) != draft.shipping_fee:
            delivery["deliveryFee"] = (
                {"deliveryFeeType": "FREE"}
                if draft.shipping_fee <= 0
                else {
                    "deliveryFeeType": "PAID",
                    "baseFee": draft.shipping_fee,
                    "deliveryFeePayType": fee.get("deliveryFeePayType") or "PREPAID",
                }
            )


def update(draft: ProductDraft) -> dict:
    """등록된 상품에 검토 화면의 수정 내용을 반영한다.

    네이버는 요청에 빠진 정보를 지워 버리므로, 현재 상품을 조회해 우리가 다루는 값만
    바꾼 뒤 통째로 다시 보낸다.
    """
    if not draft.naver_origin_product_no:
        raise WrongStateError("아직 스마트스토어에 등록되지 않은 상품입니다.")
    validate(draft)
    client = get_client()
    current = fetch_origin(client, draft.naver_origin_product_no)
    apply_to_origin(current["originProduct"], draft, _naver_image_urls(client, _ordered_images(draft)))
    payload = {k: current[k] for k in _PRODUCT_PARTS if current.get(k)}
    return _send_with_tag_retry(
        lambda p: client.update_origin_product(draft.naver_origin_product_no, p), payload
    )


def delete(draft: ProductDraft) -> None:
    """스마트스토어에서 상품을 삭제한다. 이미 없으면 로컬 기록만 지우도록 조용히 넘어간다."""
    if not draft.naver_origin_product_no:
        raise WrongStateError(
            "스마트스토어에 등록되지 않은 상품입니다. 초안은 내 작업에서 지워 주세요."
        )
    try:
        get_client().delete_origin_product(draft.naver_origin_product_no)
    except NaverApiError as e:
        if e.status != 404:
            raise
        logger.info("이미 스마트스토어에서 삭제된 상품 — 로컬 기록만 지웁니다: %s", draft.naver_origin_product_no)
