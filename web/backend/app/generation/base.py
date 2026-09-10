from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

# 진행률 콜백: (완료된 스텝 key, 0.0~1.0 전체 진행률)
ProgressCallback = Callable[[str | None, float], Awaitable[None]]


@dataclass
class ImageRef:
    id: str
    url: str
    filename: str = ""


@dataclass
class DocumentDraft:
    """생성 결과. 라우터가 이걸 Document + ChatMessage 로 저장한다."""

    title: str
    sections: list[dict[str, Any]]
    thumbnail_url: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProductDraftData:
    """상품등록(4c) 결과. 문서가 아니라 등록 필드 묶음이다."""

    analysis: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    image_urls: list[str] = field(default_factory=list)
    representative_image_url: str | None = None
    product_name: str = ""
    brand: str = ""
    manufacturer: str = ""
    seller_code: str = ""
    category_candidates: list[dict[str, Any]] = field(default_factory=list)
    selected_category: str = ""
    price: int | None = None
    shipping_fee: int = 3000
    stock: int = 999
    options: list[dict[str, Any]] = field(default_factory=list)
    kc: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)


class GenerationProvider(Protocol):
    """생성 백엔드 교체 지점.

    지금은 MockProvider 만 구현돼 있다. Gu/Park 의 추론 서버가 준비되면
    같은 인터페이스로 RemoteProvider 를 붙이고 GENERATION_PROVIDER 만 바꾼다.
    """

    name: str

    def steps(self, job_type: str) -> list[dict[str, str]]:
        """생성 중 화면(2b)의 스텝 체크리스트 정의."""
        ...

    async def generate(
        self,
        *,
        job_type: str,
        form: dict[str, Any],
        images: list[ImageRef],
        on_progress: ProgressCallback,
    ) -> "DocumentDraft | ProductDraftData": ...
