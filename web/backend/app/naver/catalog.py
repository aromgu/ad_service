"""네이버 카테고리 캐시.

말단 카테고리가 5천 개 남짓이고 자주 바뀌지 않아 프로세스 메모리에 담아 둔다.
상품 등록에는 이 목록의 `id`(leafCategoryId)가 반드시 필요하다.
"""

import logging
import threading
import time

from app.naver.client import NaverApiError, NaverCommerceClient

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60 * 60 * 12
_lock = threading.Lock()
_cache: tuple[float, list[dict]] | None = None

# 카테고리 경로 → 상품정보제공고시 상품군.
# 앞에서부터 먼저 맞는 것을 쓴다. 못 찾으면 ETC.
_NOTICE_BY_KEYWORD: list[tuple[str, str]] = [
    ("화장품", "COSMETIC"),
    ("바디", "COSMETIC"),
    ("헤어", "COSMETIC"),
    ("가방", "BAG"),
    ("신발", "SHOES"),
    ("의류", "WEAR"),
    ("패션잡화", "FASHION_ITEMS"),
    ("주방", "KITCHEN_UTENSILS"),
    ("가구", "FURNITURE"),
    ("침구", "SLEEPING_GEAR"),
    ("식품", "FOOD"),
    ("건강식품", "DIET_FOOD"),
    ("도서", "BOOKS"),
    ("스포츠", "SPORTS_EQUIPMENT"),
    ("악기", "MUSICAL_INSTRUMENT"),
    ("출산", "KIDS"),
    ("유아", "KIDS"),
]


def leaf_categories(client: NaverCommerceClient) -> list[dict]:
    global _cache
    with _lock:
        if _cache and time.time() - _cache[0] < _TTL_SECONDS:
            return _cache[1]
    cats = client.get_leaf_categories()
    with _lock:
        _cache = (time.time(), cats)
    return cats


def search(client: NaverCommerceClient, keyword: str, limit: int = 8) -> list[dict]:
    """이름에 keyword 가 들어간 말단 카테고리. 짧은 경로를 먼저 보여준다."""
    needle = keyword.strip()
    if not needle:
        return []
    try:
        cats = leaf_categories(client)
    except NaverApiError:
        logger.warning("네이버 카테고리 조회 실패 — 검색 결과를 비웁니다", exc_info=True)
        return []

    exact = [c for c in cats if c.get("name") == needle]
    partial = [c for c in cats if needle in c.get("wholeCategoryName", "") and c not in exact]
    hits = exact + sorted(partial, key=lambda c: len(c.get("wholeCategoryName", "")))
    return [
        {"id": c["id"], "path": c["wholeCategoryName"].replace(">", " › ")}
        for c in hits[:limit]
    ]


def path_of(client: NaverCommerceClient, leaf_id: str) -> str:
    """카테고리 ID 의 전체 경로 ("화장품/미용 › 스킨케어 › …"). 못 찾으면 ID 라도 보여 준다."""
    try:
        cats = leaf_categories(client)
    except NaverApiError:
        logger.warning("네이버 카테고리 조회 실패 — ID 로 대신 표시합니다", exc_info=True)
        cats = []
    for c in cats:
        if str(c.get("id")) == str(leaf_id):
            return c.get("wholeCategoryName", "").replace(">", " › ")
    return f"카테고리 {leaf_id}"


def notice_type_for(category_path: str) -> str:
    """카테고리 경로로 상품정보제공고시 상품군을 고른다."""
    for keyword, notice in _NOTICE_BY_KEYWORD:
        if keyword in category_path:
            return notice
    return "ETC"
