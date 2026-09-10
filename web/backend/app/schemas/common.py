from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: str
    email: str
    name: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- assets ----------
class AssetOut(ORMModel):
    id: str
    kind: str
    filename: str
    url: str
    content_type: str
    size_bytes: int


class ImageEditRequest(BaseModel):
    """3a-2 AI 사진 편집 팝업."""

    prompt: str = Field(min_length=1, max_length=1000)
    count: int = Field(default=4, ge=1, le=4)
    source_ids: list[str] = Field(default_factory=list, max_length=50)


# ---------- jobs ----------
Tone = Literal["감성적", "정보 중심"]


class DetailPageForm(BaseModel):
    """프론트 `generationForm` 과 대응. 필수 필드는 2a 화면의 `*` 표시와 동일."""

    product_name: str = Field(min_length=1, max_length=120)
    target: str = Field(min_length=1, max_length=60)
    language: str = "자동"
    tone: Tone = "감성적"
    length: str = "숏(10장 내외)"
    features: str = Field(min_length=1, max_length=2000)
    advanced: dict[str, Any] = Field(default_factory=dict)


class BlogForm(BaseModel):
    """3a. 상품 사진 1~8장."""

    topic: str = Field(min_length=1, max_length=200)
    style: str = "기본 블로그"
    extra_request: str = Field(default="", max_length=2000)


class ShippingSettings(BaseModel):
    """4a 배송 설정. 사용자별로 저장돼 다음 등록에 재사용된다."""

    origin_address: str = Field(default="", max_length=300)
    return_address: str = Field(default="", max_length=300)
    return_same_as_origin: bool = True
    shipping_fee: int = Field(default=3000, ge=0)
    return_fee: int = Field(default=3000, ge=0)
    exchange_fee: int = Field(default=6000, ge=0)
    cs_phone: str = Field(default="", max_length=40)
    courier: str = "CJ대한통운"


class ProductRegForm(BaseModel):
    """4a. 상세페이지 이미지 + 선택 입력 상품 정보 + 배송 설정."""

    product_info: str = Field(default="", max_length=4000)
    shipping: ShippingSettings = Field(default_factory=ShippingSettings)
    # auto  — 4c 를 건너뛰고 분석 후 바로 등록
    # review— 4c 검토 화면을 거친다
    submit_mode: Literal["auto", "review"] = "review"


# 장수 상·하한은 라우터의 IMAGE_RULES 에서 판단한다 (사용자에게 보여줄 메시지가 타입마다 다르므로).
# 여기 max_length 는 비정상적으로 큰 배열만 막는 안전장치다.
_MAX_IMAGE_IDS = 50


class DetailPageJobCreate(BaseModel):
    type: Literal["detail_page"] = "detail_page"
    form: DetailPageForm
    image_ids: list[str] = Field(default_factory=list, max_length=_MAX_IMAGE_IDS)


class BlogJobCreate(BaseModel):
    type: Literal["blog"]
    form: BlogForm
    image_ids: list[str] = Field(default_factory=list, max_length=_MAX_IMAGE_IDS)


class ProductRegJobCreate(BaseModel):
    type: Literal["product_reg"]
    form: ProductRegForm
    image_ids: list[str] = Field(default_factory=list, max_length=_MAX_IMAGE_IDS)
    # 2c 에디터의 "이 상세페이지로 상품등록" — 상세페이지 입력값·이미지를 그대로 이어받는다.
    from_document_id: str | None = None


JobCreate = Annotated[
    DetailPageJobCreate | BlogJobCreate | ProductRegJobCreate,
    Field(discriminator="type"),
]


class JobStep(BaseModel):
    key: str
    label: str
    state: Literal["done", "active", "pending"]


class JobOut(ORMModel):
    id: str
    type: str
    status: str
    progress: float
    steps: list[JobStep]
    document_id: str | None = None
    product_draft_id: str | None = None
    # 상품등록에서 4c 를 건너뛸지 판단하는 값 (form 에 들어 있다)
    submit_mode: str | None = None
    error: str | None = None
    created_at: datetime

    @classmethod
    def from_job(cls, job) -> "JobOut":
        out = cls.model_validate(job)
        out.submit_mode = (job.form or {}).get("submit_mode")
        return out


# ---------- documents ----------
class Section(BaseModel):
    id: str
    # eyebrow | headline | stat | subclaim | image | note
    type: str
    visible: bool = True
    content: dict[str, Any] = Field(default_factory=dict)


class DocumentOut(ORMModel):
    id: str
    type: str
    title: str
    sections: list[Section]
    thumbnail_url: str | None = None
    updated_at: datetime


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    sections: list[Section] | None = None


class ChatMessageOut(ORMModel):
    id: str
    role: str
    content: str
    meta: dict[str, Any]
    created_at: datetime


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    messages: list[ChatMessageOut]
    document: DocumentOut


# ---------- workspace ----------
class WorkspaceItem(BaseModel):
    id: str          # document_id 가 있으면 그것, 없으면 job_id
    job_id: str
    document_id: str | None
    product_draft_id: str | None = None
    type: str
    status: str
    progress: float
    title: str
    thumbnail_url: str | None
    created_at: datetime


# ---------- product drafts ----------
class CategoryCandidate(BaseModel):
    path: str
    confidence: int = 0


class ProductOption(BaseModel):
    name: str = Field(max_length=120)
    price: int = 0
    stock: int = 0


class KcInfo(BaseModel):
    # has — 인증 있음 / none — 인증 없음
    mode: Literal["has", "none"] = "none"
    detail: str = "KC 대상 아님"
    cert_number: str = ""


class ProductDraftOut(ORMModel):
    id: str
    status: str
    analysis: dict[str, Any]
    description: str
    image_urls: list[str]
    representative_image_url: str | None
    product_name: str
    exclude_brand_from_name: bool
    brand: str
    manufacturer: str
    seller_code: str
    category_candidates: list[CategoryCandidate]
    selected_category: str
    price: int | None
    discount_rate: int
    shipping_fee: int
    stock: int
    options: list[ProductOption]
    kc: KcInfo
    tags: list[str]
    attributes: dict[str, str]
    shipping: dict[str, Any]
    registered_at: datetime | None
    updated_at: datetime


class ProductDraftPatch(BaseModel):
    """4c 검토 화면의 부분 수정. 보낸 필드만 반영된다."""

    description: str | None = Field(default=None, max_length=4000)
    representative_image_url: str | None = None
    product_name: str | None = Field(default=None, max_length=200)
    exclude_brand_from_name: bool | None = None
    brand: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=120)
    seller_code: str | None = Field(default=None, max_length=60)
    selected_category: str | None = Field(default=None, max_length=200)
    price: int | None = Field(default=None, ge=0)
    discount_rate: int | None = Field(default=None, ge=0, le=100)
    shipping_fee: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)
    options: list[ProductOption] | None = None
    kc: KcInfo | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    attributes: dict[str, str] | None = None
