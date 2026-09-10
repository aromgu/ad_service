"""ProductDraft 를 실제 네이버 스마트스토어에 등록한다."""

import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import SHARED_IMAGE_DIR, settings
from app.db.models import ProductDraft
from app.naver import catalog
from app.naver.client import NaverApiError, NaverCommerceClient
from app.naver.product_builder import build_notice, build_payload

logger = logging.getLogger(__name__)

_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}


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


def register(draft: ProductDraft) -> dict:
    """등록 후 {originProductNo, smartstoreChannelProductNo} 를 돌려준다.

    실패는 NaverApiError 로 올려 보내 라우터가 사용자에게 그대로 보여준다.
    """
    if not draft.selected_category_id:
        raise NaverApiError(
            "네이버 카테고리를 선택해 주세요. 카테고리 검색에서 고르면 등록에 필요한 ID가 함께 저장됩니다."
        )

    if not settings.naver_register_live:
        # 연습 모드 — 외부 호출을 하나도 하지 않는다. 테스트도 이 경로로 돈다.
        logger.info("NAVER_REGISTER_LIVE=false — 실제 등록을 건너뜁니다")
        return {"originProductNo": "", "smartstoreChannelProductNo": "", "dryRun": True}

    client = get_client()

    # 1) 이미지를 네이버로 옮긴다. 외부 URL 직접 입력은 거부된다.
    files: list[tuple[str, bytes, str]] = []
    for url in draft.image_urls[:10]:
        path = _local_path(url)
        if path and path.is_file():
            files.append((path.name, path.read_bytes(), _CONTENT_TYPES.get(path.suffix.lower(), "image/jpeg")))
    if not files:
        raise NaverApiError("등록할 상품 이미지를 찾을 수 없습니다.")
    image_urls = client.upload_images(files)

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
        shipping=draft.shipping or {},
        seller_code=draft.seller_code,
        brand=draft.brand,
        manufacturer=draft.manufacturer,
        tags=list(draft.tags or []),
    )

    try:
        return client.register_product(payload)
    except NaverApiError as e:
        # 검색 태그는 상품명·카테고리와 겹치면 거부된다. 태그만 빼고 한 번 더 시도한다.
        if e.status == 400 and "sellerTags" in (e.body or ""):
            logger.info("검색 태그가 거부되어 태그 없이 재시도합니다")
            payload["originProduct"]["detailAttribute"].pop("seoInfo", None)
            return client.register_product(payload)
        raise
