import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 4a 배송 설정 — "한 번 저장하면 다음 등록에도 그대로 쓰입니다"
    shipping_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    jobs: Mapped[list["Job"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Asset(Base):
    """업로드된 상품 이미지 또는 생성 결과 이미지."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    # uploaded | generated | sample
    kind: Mapped[str] = mapped_column(String(20), default="uploaded")
    filename: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(80), default="image/png")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    """생성 작업. 프론트의 `generationJob` 상태와 1:1로 대응한다."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # detail_page | product_reg | blog
    type: Mapped[str] = mapped_column(String(20), default="detail_page")
    # queued | running | done | failed | canceled
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    form: Mapped[dict] = mapped_column(JSON, default=dict)
    image_ids: Mapped[list] = mapped_column(JSON, default=list)
    # 2c 에디터에서 넘어온 상품등록 작업의 출처 문서. 재시도 때 이미지를 다시 끌어온다.
    source_document_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True, index=True
    )
    # 상품등록(product_reg) 작업의 결과. detail_page/blog 는 document_id 를 쓴다.
    product_draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_drafts.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="jobs")
    document: Mapped["Document | None"] = relationship(foreign_keys=[document_id])
    product_draft: Mapped["ProductDraft | None"] = relationship(foreign_keys=[product_draft_id])


class Document(Base):
    """생성된 상세페이지/블로그 문서. sections 는 블록 배열."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(20), default="detail_page")
    title: Mapped[str] = mapped_column(String(200), default="제목 없는 상세페이지")
    sections: Mapped[list] = mapped_column(JSON, default=list)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    """에디터 좌측 채팅 스레드의 메시지 한 건."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    # user | assistant
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # 접힌 툴 스텝 행 / 답변 요약 카드 등 부가 UI 데이터
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="messages")


class ProductDraft(Base):
    """AI 상품등록(4c)의 검토 대상. 네이버 커머스에 올릴 등록 정보 한 벌.

    상세페이지/블로그와 달리 결과물이 문서가 아니라 구조화된 필드 묶음이라
    Document 와 분리했다.
    """

    __tablename__ = "product_drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # draft | registered
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # 내 작업 카드에 보이는 이름. 상품명과 별개로 사용자가 고칠 수 있다.
    title: Mapped[str] = mapped_column(String(200), default="")

    # AI 분석 결과 요약 (4c 상단 배너)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)

    description: Mapped[str] = mapped_column(Text, default="")
    image_urls: Mapped[list] = mapped_column(JSON, default=list)
    representative_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    product_name: Mapped[str] = mapped_column(String(200), default="")
    exclude_brand_from_name: Mapped[bool] = mapped_column(Boolean, default=False)
    brand: Mapped[str] = mapped_column(String(120), default="")
    manufacturer: Mapped[str] = mapped_column(String(120), default="")
    seller_code: Mapped[str] = mapped_column(String(60), default="")

    # [{id, path, confidence}] — id 는 네이버 leafCategoryId
    category_candidates: Mapped[list] = mapped_column(JSON, default=list)
    selected_category: Mapped[str] = mapped_column(String(200), default="")
    # 네이버 등록에 반드시 필요한 말단 카테고리 ID
    selected_category_id: Mapped[str] = mapped_column(String(20), default="")

    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_rate: Mapped[int] = mapped_column(Integer, default=0)
    shipping_fee: Mapped[int] = mapped_column(Integer, default=3000)
    stock: Mapped[int] = mapped_column(Integer, default=999)

    # [{name, price, stock}]
    options: Mapped[list] = mapped_column(JSON, default=list)
    # {mode: 'has'|'none', detail: 'not_target'|...}
    kc: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # {사용대상, 패턴, 주요소재 ...}
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    # 등록 시점의 배송 설정 스냅샷
    shipping: Mapped[dict] = mapped_column(JSON, default=dict)

    # 네이버 등록 결과
    naver_origin_product_no: Mapped[str] = mapped_column(String(30), default="")
    naver_channel_product_no: Mapped[str] = mapped_column(String(30), default="")

    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
