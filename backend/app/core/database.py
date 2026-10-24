from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Engine — один на всё приложение: держит пул соединений с PostgreSQL
engine = create_async_engine(settings.database_url, echo=settings.db_echo)

# Фабрика сессий. expire_on_commit=False — после commit объекты остаются читаемыми
# без повторного запроса в БД (в async ленивая подгрузка всё равно невозможна)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: одна сессия на один HTTP-запрос, закрывается автоматически."""
    async with SessionLocal() as session:
        yield session
