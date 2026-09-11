from pydantic import Field

from ad_service.api.schemas.generation import StrictModel


class ProductPlacement(StrictModel):
    # x/y는 상품이 화면 안에 머물 수 있는 이동 범위의 비율입니다.
    x: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    y: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    height: float = Field(default=0.72, ge=0.1, le=0.95, allow_inf_nan=False)
    shadow: float = Field(default=0.24, ge=0, le=0.6, allow_inf_nan=False)


class TextPlacement(StrictModel):
    visible: bool = True
    headline: str = Field(default="", max_length=80)
    body: str = Field(default="", max_length=300)
    cta: str = Field(default="", max_length=24)
    x: float = Field(default=0.05, ge=0, le=0.85, allow_inf_nan=False)
    y: float = Field(default=0.07, ge=0, le=0.85, allow_inf_nan=False)
    width: float = Field(default=0.46, ge=0.15, le=0.95, allow_inf_nan=False)
    headline_size: int = Field(default=66, ge=20, le=96)
    body_size: int = Field(default=30, ge=14, le=56)
    color: str = Field(default="#1e1e24", pattern=r"^#[0-9a-fA-F]{6}$")


class EditorScene(StrictModel):
    version: int = Field(default=1, ge=1, le=1)
    product: ProductPlacement = Field(default_factory=ProductPlacement)
    text: TextPlacement = Field(default_factory=TextPlacement)
