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
    background_remover: str = "simple"
    image_quality: str = "medium"
    budget_cap_usd: float = Field(default=10.0, gt=0, le=30)


@lru_cache
def get_settings() -> Settings:
    return Settings()
