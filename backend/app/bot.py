"""Telegram-бот: python -m app.bot

Long polling, а не webhook: боту не нужен публичный адрес, поэтому он работает и локально.
"""

import asyncio
import logging

import httpx

from app.core.config import settings
from app.core.database import SessionLocal
from app.services import telegram

logger = logging.getLogger("walletly.bot")
_POLL_SECONDS = 30
_RETRY_SECONDS = 5


async def _process(update: dict) -> None:
    async with SessionLocal() as session:
        reply = await telegram.handle_update(session, update)
    if reply:
        await telegram.send_message(*reply)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # httpx на уровне INFO печатает адрес запроса, а в адресе секретный токен бота
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not telegram.is_configured():
        logger.info("TELEGRAM_BOT_TOKEN не задан, бот выключен")
        await asyncio.Event().wait()

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
    offset = 0
    async with httpx.AsyncClient(timeout=_POLL_SECONDS + 10) as client:
        while True:
            try:
                response = await client.get(url, params={"offset": offset, "timeout": _POLL_SECONDS})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Telegram не ответил: %s", type(exc).__name__)
                await asyncio.sleep(_RETRY_SECONDS)
                continue
            for update in response.json().get("result", []):
                # Сдвигаем до обработки: сообщение с ошибкой не должно ломать бота бесконечно
                offset = update["update_id"] + 1
                try:
                    await _process(update)
                except Exception:
                    logger.exception("Ошибка при обработке сообщения")


if __name__ == "__main__":
    asyncio.run(main())
