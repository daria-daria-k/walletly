"""Telegram: привязка аккаунта, разбор сообщений боту и отправка уведомлений."""

import logging
import re
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import settings
from app.models import Account, Category, Ledger, Transaction, User
from app.models.enums import LedgerType, Plan, TransactionType
from app.services.account import list_accounts
from app.services.billing import get_plan
from app.services.ml import predict_for_import

logger = logging.getLogger(__name__)

_LINK_TTL = 10 * 60
_NUMBER = r"\d+(?:[.,]\d{1,2})?"
_EXPENSE = re.compile(rf"^(?:(?P<a1>{_NUMBER})\s+(?P<d1>.+)|(?P<d2>.+?)\s+(?P<a2>{_NUMBER}))$")

HELP = (
    "Напишите расход одним сообщением, например: кофе 250\n"
    "/balance — остатки на счетах\n"
    "/help — эта подсказка"
)


def is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_bot_username)


async def create_link_url(user_id: int) -> str:
    code = secrets.token_urlsafe(24)
    await rate_limit.set_value(f"tg-link:{code}", str(user_id), _LINK_TTL)
    return f"https://t.me/{settings.telegram_bot_username}?start={code}"


async def unlink(session: AsyncSession, user: User) -> None:
    user.telegram_chat_id = None
    await session.commit()


async def send_message(chat_id: int, text: str) -> None:
    if not settings.telegram_bot_token:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        # Только тип ошибки: в её тексте есть адрес запроса, а в нём секретный токен бота
        logger.warning("Не удалось отправить сообщение в Telegram: %s", type(exc).__name__)


def parse_expense(text: str) -> tuple[Decimal, str] | None:
    match = _EXPENSE.match(" ".join(text.split()))
    if match is None:
        return None
    raw = match["a1"] or match["a2"]
    description = (match["d1"] or match["d2"]).strip()
    try:
        amount = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None
    if amount <= 0 or len(description) > 500:
        return None
    return amount, description


async def _personal_ledger(session: AsyncSession, user_id: int) -> int:
    return await session.scalar(
        select(Ledger.id).where(Ledger.owner_id == user_id, Ledger.type == LedgerType.PERSONAL)
    )


async def _link(session: AsyncSession, chat_id: int, code: str) -> str:
    user_id = await rate_limit.pop_value(f"tg-link:{code}")
    user = await session.get(User, int(user_id)) if user_id else None
    if user is None or not user.is_active:
        return "Ссылка устарела. Откройте новую в настройках Walletly."
    # Чат может быть привязан только к одному аккаунту, колонка уникальная
    await session.execute(
        update(User).where(User.telegram_chat_id == chat_id).values(telegram_chat_id=None)
    )
    user.telegram_chat_id = chat_id
    await session.commit()
    return f"Готово, {user.name}! Telegram подключён.\n{HELP}"


async def _balance(session: AsyncSession, ledger_id: int) -> str:
    accounts = await list_accounts(session, ledger_id)
    if not accounts:
        return "Счетов пока нет. Добавьте их в приложении."
    return "\n".join(f"{item.name}: {item.balance:,.2f} {item.currency}".replace(",", " ") for item in accounts)


async def _add_expense(session: AsyncSession, user: User, ledger_id: int, text: str) -> str:
    parsed = parse_expense(text)
    if parsed is None:
        return f"Не понял сообщение.\n{HELP}"
    amount, description = parsed
    account = await session.scalar(
        select(Account)
        .where(Account.ledger_id == ledger_id, Account.is_active.is_(True))
        .order_by(Account.sort_order, Account.id)
        .limit(1)
    )
    if account is None:
        return "Сначала добавьте счёт в приложении."
    category_id = (await predict_for_import(session, ledger_id, [description])).get(description)
    if category_id is None:
        # Лучше спросить, чем молча записать в случайную категорию и исказить аналитику
        return "Не смог определить категорию. Добавьте эту операцию в приложении: так модель научится."
    category = await session.get(Category, category_id)
    session.add(
        Transaction(
            ledger_id=ledger_id,
            user_id=user.id,
            type=TransactionType.EXPENSE,
            amount=amount,
            account_id=account.id,
            category_id=category_id,
            description=description,
            tx_date=date.today(),
        )
    )
    await session.commit()
    return f"Записал расход {amount} {account.currency}: {category.name}, счёт «{account.name}»"


async def handle_update(session: AsyncSession, update_data: dict) -> tuple[int, str] | None:
    """Возвращает чат и ответ. Отправка отдельно: так логику можно проверить без сети."""
    message = update_data.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return None

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            return chat_id, await _link(session, chat_id, parts[1])
        return chat_id, "Подключите бота в настройках Walletly: раздел «Уведомления»."

    # Кто пишет, определяет только привязка: бот открыт всем в Telegram
    user = await session.scalar(select(User).where(User.telegram_chat_id == chat_id))
    if user is None or not user.is_active:
        return chat_id, "Этот чат не подключён. Откройте ссылку из настроек Walletly."
    if await get_plan(session, user.id) != Plan.PREMIUM:
        return chat_id, "Telegram-бот доступен в тарифе Premium."

    if text == "/help":
        return chat_id, HELP
    ledger_id = await _personal_ledger(session, user.id)
    if text == "/balance":
        return chat_id, await _balance(session, ledger_id)
    if text.startswith("/"):
        return chat_id, HELP
    return chat_id, await _add_expense(session, user, ledger_id, text)
