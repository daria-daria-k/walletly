from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Category, CategoryGroup, Transaction
from app.models.enums import TransactionType
from app.schemas.transaction import AnalyticsSummary, CategoryTotal, MonthTotal

# Переводы в аналитику не входят: это перемещение своих денег, а не доход и не расход
_REAL_TYPES = (TransactionType.INCOME, TransactionType.EXPENSE)


def _scoped(query, ledger_id: int, currency: str, date_from: date | None, date_to: date | None):
    # Валюту фиксируем явно: сумма рублей и долларов — бессмысленное число
    query = query.join(Account, Transaction.account_id == Account.id).where(
        Transaction.ledger_id == ledger_id,
        Transaction.is_deleted.is_(False),
        Account.currency == currency,
    )
    if date_from:
        query = query.where(Transaction.tx_date >= date_from)
    if date_to:
        query = query.where(Transaction.tx_date <= date_to)
    return query


async def summary(
    session: AsyncSession,
    ledger_id: int,
    currency: str,
    date_from: date | None,
    date_to: date | None,
) -> AnalyticsSummary:
    rows = await session.execute(
        _scoped(
            select(Transaction.type, func.sum(Transaction.amount))
            .where(Transaction.type.in_(_REAL_TYPES))
            .group_by(Transaction.type),
            ledger_id,
            currency,
            date_from,
            date_to,
        )
    )
    totals = dict(rows.all())
    income = totals.get(TransactionType.INCOME, Decimal(0))
    expense = totals.get(TransactionType.EXPENSE, Decimal(0))
    return AnalyticsSummary(income=income, expense=expense, net=income - expense)


async def by_category(
    session: AsyncSession,
    ledger_id: int,
    tx_type: TransactionType,
    currency: str,
    date_from: date | None,
    date_to: date | None,
) -> list[CategoryTotal]:
    total = func.sum(Transaction.amount)
    rows = await session.execute(
        _scoped(
            select(Category.id, Category.name, CategoryGroup.name, total)
            .join(Category, Transaction.category_id == Category.id)
            .join(CategoryGroup, Category.category_group_id == CategoryGroup.id)
            .where(Transaction.type == tx_type)
            .group_by(Category.id, Category.name, CategoryGroup.name)
            .order_by(total.desc()),
            ledger_id,
            currency,
            date_from,
            date_to,
        )
    )
    return [
        CategoryTotal(category_id=row[0], category_name=row[1], group_name=row[2], total=row[3])
        for row in rows
    ]


async def monthly(
    session: AsyncSession,
    ledger_id: int,
    currency: str,
    date_from: date | None,
    date_to: date | None,
) -> list[MonthTotal]:
    month = func.to_char(Transaction.tx_date, "YYYY-MM")
    rows = await session.execute(
        _scoped(
            select(month, Transaction.type, func.sum(Transaction.amount))
            .where(Transaction.type.in_(_REAL_TYPES))
            .group_by(month, Transaction.type)
            .order_by(month),
            ledger_id,
            currency,
            date_from,
            date_to,
        )
    )
    months: dict[str, MonthTotal] = {}
    for key, tx_type, value in rows:
        entry = months.setdefault(
            key, MonthTotal(month=key, income=Decimal(0), expense=Decimal(0))
        )
        setattr(entry, tx_type.value, value)
    return list(months.values())
