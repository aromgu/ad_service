from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AD_", extra="ignore")

    app_name: str = "ad_service"
    environment: str = "development"
    output_root: Path = Path("data/outputs/api")
    copy_provider: str = "mock"
    image_provider: str = "mock"
    # 기본 Mock 서버는 GPU 없이 실행합니다. 실제 배포에서는 AD_BACKGROUND_REMOVER=auto로
    # 바꾸면 박스 유무에 따라 SAM2/BiRefNet이 자동 선택됩니다.
    background_remover: str = "simple"
    image_quality: str = "medium"
    budget_cap_usd: float = Field(default=10.0, gt=0, le=30)


@lru_cache
def get_settings() -> Settings:
    return Settings()
