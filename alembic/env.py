import asyncio
from logging.config import fileConfig
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# 상위 경로 모듈 인식 허용
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ad_service.database import Base
from src.ad_service.core.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 환경 변수나 설정에서 비동기 URL 강제 매핑
database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@db:5432/dbname")
if "postgresql://" in database_url and "+asyncpg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
elif "+psycopg2" in database_url:
    database_url = database_url.replace("+psycopg2", "+asyncpg")

config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()