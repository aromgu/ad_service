from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
# web/images — 로고·샘플·생성 결과 이미지 공용 저장소 (CLAUDE.md 기준 내 소유 디렉터리)
SHARED_IMAGE_DIR = BACKEND_DIR.parent / "images"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 60 * 24 * 7
    allow_demo_user: bool = True

    database_url: str = "sqlite:///./data/app.db"
    upload_dir: str = "./uploads"

    generation_provider: str = "mock"
    remote_generation_url: str = "http://localhost:8100"
    mock_duration_seconds: float = 12.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def sqlalchemy_url(self) -> str:
        """상대 경로 sqlite URL 을 백엔드 디렉터리 기준 절대 경로로 정규화한다."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            raw = self.database_url[len(prefix) :]
            if not raw.startswith("/"):
                return f"{prefix}{(BACKEND_DIR / raw).resolve()}"
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
