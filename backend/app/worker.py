"""Фоновые задачи по расписанию: python -m app.worker

Отдельный процесс, а не часть API: при нескольких воркерах uvicorn задача запустилась бы
в каждом из них.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.database import SessionLocal
from app.services.auth import delete_stale_tokens

logger = logging.getLogger("walletly.worker")


async def cleanup_tokens() -> None:
    async with SessionLocal() as session:
        deleted = await delete_stale_tokens(session)
    logger.info("Удалено устаревших токенов: %s", deleted)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(cleanup_tokens, "cron", hour=3, minute=0)
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_scheduler().start()
    logger.info("Планировщик запущен")
    await asyncio.Event().wait()  # работаем, пока процесс не остановят


if __name__ == "__main__":
    asyncio.run(main())
