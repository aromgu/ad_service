"""앱 설정. 환경변수 ``AD_`` 프리픽스 또는 ``.env`` 로 오버라이드한다."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AD_", extra="ignore")

    app_name: str = "ad_service"
    app_version: str = "0.1.0"
    environment: str = "development"

    log_level: str = "INFO"
    log_json: bool = False  # 운영에서 true → 한 줄 JSON 로그

    # CORS 허용 오리진. 콤마로 구분한 문자열. 기본은 개발용으로 전체 허용("*").
    cors_allow_origins: str = "*"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    # 생성 결과(이미지)가 저장되고 /assets 로 서빙되는 루트.
    output_root: Path = Path("data/outputs/api")

    # 업로드 입력 이미지 임시 저장 위치.
    upload_root: Path = Path("data/uploads")
    max_upload_mb: int = 10

    # 완료된 job 을 메모리에 보관하는 시간(초). 기본 24시간.
    job_ttl_seconds: int = 24 * 60 * 60

    # 생성 요청 1건이 쓸 수 있는 예산 상한(USD).
    budget_cap_usd: float = Field(default=10.0, gt=0, le=30)

    # 문구/이미지 공급자. MVP 는 mock 고정. (실제 모델은 모델 담당이 연결)
    copy_provider: str = "mock"
    image_provider: str = "mock"

    @property
    def text_max_chars(self) -> int:
        """API 명세서 D10: 제품 설명 최대 길이."""

        return 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
