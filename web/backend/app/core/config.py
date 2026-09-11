from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
# web/web-images — 로고·샘플·생성 결과 이미지 공용 저장소.
# 폴더 이름과 달리 URL 은 /static/images 로 서빙한다 (문서에 저장된 주소를 깨지 않기 위해).
SHARED_IMAGE_DIR = BACKEND_DIR.parent / "web-images"


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

    # ===== 네이버 커머스 API =====
    # 호스트는 공통 규격 문서 기준. 경로는 /external/... 로 시작한다.
    naver_api_base: str = "https://api.commerce.naver.com/external"
    naver_client_id: str = ""
    naver_client_secret: str = ""
    # SELF — 내 스토어 / SELLER — 대행. SELLER 일 때만 account_id 를 보낸다.
    naver_account_type: str = "SELF"
    naver_account_id: str = ""

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
