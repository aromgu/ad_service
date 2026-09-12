from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 데이터베이스 접속 URL (환경 변수나 .env 파일에서 불러오거나 기본값 사용)
    DATABASE_URL: str = "postgresql+psycopg2://user:password@localhost:5432/dbname"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()