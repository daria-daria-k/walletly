from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Transaction
from app.models.enums import TransactionType
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate
from app.services.errors import ConflictError
from app.services.scoped import get_in_ledger


def _to_read(account: Account, balance: Decimal, month_change: Decimal) -> AccountRead:
    return AccountRead(
        id=account.id,
        name=account.name,
        currency=account.currency,
        initial_balance=account.initial_balance,
        balance=balance,
        month_change=month_change,
        is_active=account.is_active,
        sort_order=account.sort_order,
    )


def _balances_query():
    # Одна строка операции влияет на остаток по-разному в зависимости от того,
    # каким счётом она присоединилась: для перевода это и «откуда», и «куда»
    delta = case(
        (
            and_(Transaction.account_id == Account.id, Transaction.type == TransactionType.INCOME),
            Transaction.amount,
        ),
        (Transaction.to_account_id == Account.id, Transaction.amount),
        else_=-Transaction.amount,
    )
    return (
        select(
            Account,
            Account.initial_balance + func.coalesce(func.sum(delta), 0),
            # FILTER: тем же проходом по операциям считаем сумму только за этот месяц
            func.coalesce(
                func.sum(delta).filter(Transaction.tx_date >= date.today().replace(day=1)), 0
            ),
        )
        # LEFT JOIN: счёт без операций тоже должен попасть в результат
        .outerjoin(
            Transaction,
            and_(
                or_(Transaction.account_id == Account.id, Transaction.to_account_id == Account.id),
                Transaction.is_deleted.is_(False),
            ),
        )
        .group_by(Account.id)
    )


async def list_accounts(
    session: AsyncSession, ledger_id: int, include_archived: bool = False
) -> list[AccountRead]:
    query = _balances_query().where(Account.ledger_id == ledger_id)
    if not include_archived:
        query = query.where(Account.is_active.is_(True))
    rows = await session.execute(query.order_by(Account.sort_order, Account.id))
    return [_to_read(*row) for row in rows]


async def _read_one(session: AsyncSession, account_id: int) -> AccountRead:
    row = (await session.execute(_balances_query().where(Account.id == account_id))).one()
    return _to_read(*row)


async def create_account(session: AsyncSession, ledger_id: int, data: AccountCreate) -> AccountRead:
    account = Account(ledger_id=ledger_id, **data.model_dump())
    session.add(account)
    await session.commit()
    return await _read_one(session, account.id)


async def update_account(
    session: AsyncSession, ledger_id: int, account_id: int, data: AccountUpdate
) -> AccountRead:
    account = await get_in_ledger(session, Account, ledger_id, account_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await session.commit()
    return await _read_one(session, account.id)


async def delete_account(session: AsyncSession, ledger_id: int, account_id: int) -> None:
    account = await get_in_ledger(session, Account, ledger_id, account_id)
    await session.delete(account)
    try:
        await session.commit()
    except IntegrityError:
        # Решает RESTRICT в БД, а не предварительный SELECT: между проверкой
        # и удалением кто-то мог бы успеть добавить операцию
        await session.rollback()
        raise ConflictError("На счёте есть операции — его можно только архивировать") from None
