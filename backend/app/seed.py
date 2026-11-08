"""Демо-данные для локальной проверки: uv run python -m app.seed

Создаёт администратора и второго участника с известными паролями, поэтому на сервере не запускается.
"""

import asyncio
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models import Account, Category, CategoryGroup, LedgerMember, Transaction, User
from app.models.enums import CategoryType, MemberRole, TransactionType, UserRole
from app.schemas.auth import RegisterRequest
from app.schemas.ledger import LedgerCreate
from app.services.auth import register_user
from app.services.ledger import create_shared_ledger

PASSWORD = "demo-password"
DEMO_EMAIL = "demo@walletly.test"
PARTNER_EMAIL = "partner@walletly.test"

EXPENSES = {
    "Продукты": (500, 4500, 9, ["Перекрёсток", "Пятёрочка", "Рынок"]),
    "Жильё и ЖКХ": (6000, 9000, 1, ["Квартплата"]),
    "Транспорт": (150, 900, 6, ["Такси", "Автобус"]),
    "Кафе и рестораны": (300, 2500, 4, ["Кофе", "Обед", "Ужин"]),
    "Развлечения": (400, 3000, 2, ["Кино", "Концерт"]),
    "Подписки": (199, 599, 2, ["Музыка", "Облако"]),
}


async def _fill_ledger(session, ledger_id: int, user_id: int, rng: random.Random) -> None:
    card = Account(ledger_id=ledger_id, name="Сбер", initial_balance=Decimal("35000"), sort_order=0)
    cash = Account(ledger_id=ledger_id, name="Наличные", initial_balance=Decimal("5000"), sort_order=1)
    session.add_all([card, cash])
    await session.flush()

    rows = await session.execute(
        select(Category, CategoryGroup.type)
        .join(CategoryGroup)
        .where(Category.ledger_id == ledger_id)
    )
    by_name = {category.name: (category, kind) for category, kind in rows}
    salary = by_name["Зарплата"][0]
    assert by_name["Зарплата"][1] == CategoryType.INCOME

    start = date.today().replace(day=1)
    for months_ago in range(6):
        month = (start - timedelta(days=30 * months_ago)).replace(day=1)
        session.add(
            Transaction(
                ledger_id=ledger_id,
                user_id=user_id,
                type=TransactionType.INCOME,
                amount=Decimal("120000"),
                account_id=card.id,
                category_id=salary.id,
                description="Зарплата",
                tx_date=month,
            )
        )
        session.add(
            Transaction(
                ledger_id=ledger_id,
                user_id=user_id,
                type=TransactionType.TRANSFER,
                amount=Decimal("5000"),
                account_id=card.id,
                to_account_id=cash.id,
                description="Снятие наличных",
                tx_date=month + timedelta(days=2),
            )
        )
        for name, (low, high, count, descriptions) in EXPENSES.items():
            for _ in range(count):
                tx_date = month + timedelta(days=rng.randint(0, 27))
                if tx_date > date.today():
                    continue
                session.add(
                    Transaction(
                        ledger_id=ledger_id,
                        user_id=user_id,
                        type=TransactionType.EXPENSE,
                        amount=Decimal(rng.randint(low, high)),
                        account_id=rng.choice([card.id, card.id, cash.id]),
                        category_id=by_name[name][0].id,
                        description=rng.choice(descriptions),
                        tx_date=tx_date,
                    )
                )


async def seed() -> None:
    if settings.cookie_secure:
        sys.exit("Похоже на продакшен (COOKIE_SECURE=true): демо-данные здесь не создаём")

    async with SessionLocal() as session:
        if await session.scalar(select(User.id).where(User.email == DEMO_EMAIL)):
            sys.exit("Демо-данные уже созданы")

        rng = random.Random(42)  # одинаковые данные при каждом пересоздании базы
        demo = await register_user(
            session, RegisterRequest(email=DEMO_EMAIL, password=PASSWORD, name="Демо")
        )
        partner = await register_user(
            session, RegisterRequest(email=PARTNER_EMAIL, password=PASSWORD, name="Партнёр")
        )
        demo.role = UserRole.ADMIN

        personal_id = await session.scalar(
            select(LedgerMember.ledger_id).where(LedgerMember.user_id == demo.id)
        )
        await _fill_ledger(session, personal_id, demo.id, rng)

        family = await create_shared_ledger(session, demo, LedgerCreate(name="Семья").name)
        session.add(
            LedgerMember(ledger_id=family.ledger_id, user_id=partner.id, role=MemberRole.MEMBER)
        )
        await _fill_ledger(session, family.ledger_id, partner.id, rng)
        await session.commit()

    await engine.dispose()
    print(f"Готово. Вход: {DEMO_EMAIL} (админ) и {PARTNER_EMAIL}, пароль: {PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
