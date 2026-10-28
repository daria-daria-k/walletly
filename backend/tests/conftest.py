"""Общие фикстуры pytest. Файл conftest.py pytest подхватывает автоматически."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import get_session
from app.main import app
from app.models import Base

# Отдельная база для тестов: тесты очищают таблицы, рабочие данные трогать нельзя
TEST_DB_URL = settings.database_url.set(database=f"{settings.postgres_db}_test")


async def _recreate_test_database() -> None:
    # CREATE/DROP DATABASE нельзя выполнить внутри транзакции — нужен AUTOCOMMIT
    admin = create_async_engine(
        settings.database_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_URL.database}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DB_URL.database}"'))
    await admin.dispose()

    # В тестах таблицы создаём по моделям: быстро и всегда совпадает с текущим кодом.
    # Сами миграции проверяет `alembic check`
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def test_database() -> None:
    """Один раз за запуск тестов: чистая тестовая БД со всеми таблицами."""
    asyncio.run(_recreate_test_database())


@pytest.fixture
def anyio_backend() -> str:
    # Плагин anyio (ставится вместе с FastAPI) запускает async-тесты в asyncio
    return "asyncio"


@pytest.fixture
async def db_engine(test_database: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    yield engine
    # После каждого теста — пустые таблицы, чтобы тесты не влияли друг на друга
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
async def session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Сессия для проверки данных в БД напрямую, в обход API."""
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
async def client(db_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент к приложению. Запросы идут в память, без реального сервера и сети."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    # Подмена зависимости: эндпоинты получат сессию к тестовой БД вместо рабочей
    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
