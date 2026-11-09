"""Фоновые задачи по расписанию: python -m app.worker

Отдельный процесс, а не часть API: при нескольких воркерах uvicorn задача запустилась бы
в каждом из них.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.database import SessionLocal
from app.ml.train import train_all
from app.models.enums import Plan
from app.services import mailer, telegram
from app.services.auth import delete_stale_tokens
from app.services.billing import get_plan
from app.services.notification import delete_old, run_checks

logger = logging.getLogger("walletly.worker")


async def cleanup_tokens() -> None:
    async with SessionLocal() as session:
        deleted = await delete_stale_tokens(session)
    logger.info("Удалено устаревших токенов: %s", deleted)


async def check_notifications() -> None:
    async with SessionLocal() as session:
        created = await run_checks(session)
    logger.info("Новых уведомлений: %s", len(created))
    for item in created:
        # По почте только недельная сводка: остальное важнее увидеть в приложении, чем в ящике
        if item.kind == "weekly" and item.user.email_verified_at is not None:
            await mailer.send_mail(item.user.email, item.title, item.body)
        if item.user.telegram_chat_id is not None:
            async with SessionLocal() as session:
                plan = await get_plan(session, item.user.id)
            if plan == Plan.PREMIUM:
                await telegram.send_message(item.user.telegram_chat_id, f"{item.title}\n{item.body}")


async def cleanup_notifications() -> None:
    async with SessionLocal() as session:
        await delete_old(session)


async def train_models() -> None:
    logger.info("Обучено пространств: %s", await train_all())


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(cleanup_tokens, "cron", hour=3, minute=0)
    scheduler.add_job(cleanup_notifications, "cron", hour=3, minute=10)
    scheduler.add_job(check_notifications, "cron", minute=5)
    scheduler.add_job(train_models, "cron", hour=2, minute=0)
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # httpx на уровне INFO печатает адрес запроса, а в адресе секретный токен бота
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build_scheduler().start()
    logger.info("Планировщик запущен")
    await asyncio.Event().wait()  # работаем, пока процесс не остановят


if __name__ == "__main__":
    asyncio.run(main())
