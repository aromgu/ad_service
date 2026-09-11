from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# check_same_thread=False — FastAPI 는 요청마다 다른 스레드를 쓸 수 있다.
engine = create_engine(
    settings.sqlalchemy_url,
    connect_args={"check_same_thread": False} if settings.sqlalchemy_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.db import models  # noqa: F401  (매핑 등록 목적)

    Base.metadata.create_all(bind=engine)
