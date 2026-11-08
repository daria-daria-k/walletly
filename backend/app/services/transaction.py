from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Account, Category, LedgerMember, Transaction
from app.models.enums import CategoryType, MemberRole, TransactionType
from app.schemas.transaction import TransactionCreate, TransactionRead, TransactionUpdate
from app.services.errors import InvalidDataError, NotFoundError, PermissionDeniedError


@dataclass(frozen=True)
class TransactionFilters:
    date_from: date | None = None
    date_to: date | None = None
    account_id: int | None = None
    category_id: int | None = None
    type: TransactionType | None = None
    search: str | None = None


def to_read(tx: Transaction) -> TransactionRead:
    return TransactionRead(
        id=tx.id,
        ledger_id=tx.ledger_id,
        user_id=tx.user_id,
        author_name=tx.author.name,
        type=tx.type,
        amount=tx.amount,
        account_id=tx.account_id,
        to_account_id=tx.to_account_id,
        category_id=tx.category_id,
        description=tx.description,
        tx_date=tx.tx_date,
        created_at=tx.created_at,
    )


def _apply_filters(query, ledger_id: int, filters: TransactionFilters):
    query = query.where(Transaction.ledger_id == ledger_id, Transaction.is_deleted.is_(False))
    if filters.date_from:
        query = query.where(Transaction.tx_date >= filters.date_from)
    if filters.date_to:
        query = query.where(Transaction.tx_date <= filters.date_to)
    if filters.account_id:
        query = query.where(
            or_(
                Transaction.account_id == filters.account_id,
                Transaction.to_account_id == filters.account_id,
            )
        )
    if filters.category_id:
        query = query.where(Transaction.category_id == filters.category_id)
    if filters.type:
        query = query.where(Transaction.type == filters.type)
    if filters.search:
        # autoescape: символы % и _ из запроса ищутся буквально, а не как шаблон LIKE
        query = query.where(Transaction.description.icontains(filters.search, autoescape=True))
    return query


async def list_transactions(
    session: AsyncSession, ledger_id: int, filters: TransactionFilters, limit: int, offset: int
) -> tuple[list[Transaction], int]:
    total = await session.scalar(
        _apply_filters(select(func.count()).select_from(Transaction), ledger_id, filters)
    )
    result = await session.scalars(
        _apply_filters(select(Transaction), ledger_id, filters)
        .options(joinedload(Transaction.author))
        # id во второй колонке: без него порядок операций за один день
        # не определён, и при пагинации строки могли бы повторяться или теряться
        .order_by(Transaction.tx_date.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result), total


async def get_transaction(session: AsyncSession, ledger_id: int, tx_id: int) -> Transaction:
    tx = await session.scalar(
        select(Transaction)
        .options(joinedload(Transaction.author))
        .where(
            Transaction.id == tx_id,
            Transaction.ledger_id == ledger_id,
            Transaction.is_deleted.is_(False),
        )
    )
    if tx is None:
        raise NotFoundError("Операция не найдена")
    return tx


async def _load_account(session: AsyncSession, ledger_id: int, account_id: int) -> Account:
    account = await session.scalar(
        select(Account).where(Account.id == account_id, Account.ledger_id == ledger_id)
    )
    if account is None:
        raise InvalidDataError("Счёт не найден в этом пространстве")
    return account


async def validate_fields(
    session: AsyncSession,
    ledger_id: int,
    tx_type: TransactionType,
    account_id: int,
    to_account_id: int | None,
    category_id: int | None,
    *,
    check_active: bool,
) -> None:
    """Правила, которые не выразить CHECK-ограничением: они смотрят в другие таблицы."""
    account = await _load_account(session, ledger_id, account_id)
    if check_active and not account.is_active:
        raise InvalidDataError("Счёт в архиве")

    if tx_type == TransactionType.TRANSFER:
        if to_account_id is None or to_account_id == account_id:
            raise InvalidDataError("Для перевода нужен другой счёт зачисления")
        if category_id is not None:
            raise InvalidDataError("У перевода не бывает категории")
        to_account = await _load_account(session, ledger_id, to_account_id)
        if check_active and not to_account.is_active:
            raise InvalidDataError("Счёт зачисления в архиве")
        # В операции одна сумма: при разных валютах она значила бы разное на двух счетах
        if to_account.currency != account.currency:
            raise InvalidDataError("Перевод возможен только между счетами в одной валюте")
        return

    if to_account_id is not None:
        raise InvalidDataError("Счёт зачисления бывает только у перевода")
    if category_id is None:
        raise InvalidDataError("Укажите категорию")
    category = await session.scalar(
        select(Category)
        .options(joinedload(Category.group))
        .where(Category.id == category_id, Category.ledger_id == ledger_id)
    )
    if category is None:
        raise InvalidDataError("Категория не найдена в этом пространстве")
    if check_active and not category.is_active:
        raise InvalidDataError("Категория в архиве")
    expected = CategoryType.INCOME if tx_type == TransactionType.INCOME else CategoryType.EXPENSE
    if category.group.type != expected:
        raise InvalidDataError("Тип категории не совпадает с типом операции")


def _ensure_can_edit(tx: Transaction, member: LedgerMember) -> None:
    is_manager = member.role in (MemberRole.OWNER, MemberRole.ADMIN)
    if tx.user_id != member.user_id and not is_manager:
        raise PermissionDeniedError("Менять чужие операции может только владелец или администратор")


async def create_transaction(
    session: AsyncSession, member: LedgerMember, data: TransactionCreate
) -> Transaction:
    await validate_fields(
        session,
        member.ledger_id,
        data.type,
        data.account_id,
        data.to_account_id,
        data.category_id,
        check_active=True,
    )
    tx = Transaction(ledger_id=member.ledger_id, user_id=member.user_id, **data.model_dump())
    session.add(tx)
    await session.commit()
    return await get_transaction(session, member.ledger_id, tx.id)


async def update_transaction(
    session: AsyncSession, member: LedgerMember, tx_id: int, data: TransactionUpdate
) -> Transaction:
    tx = await get_transaction(session, member.ledger_id, tx_id)
    _ensure_can_edit(tx, member)
    changes = data.model_dump(exclude_unset=True)

    merged = {
        field: changes.get(field, getattr(tx, field))
        for field in ("type", "account_id", "to_account_id", "category_id")
    }
    # Старую операцию на архивном счёте можно поправить (например, описание),
    # но перенести операцию НА архивный счёт нельзя
    await validate_fields(
        session,
        member.ledger_id,
        merged["type"],
        merged["account_id"],
        merged["to_account_id"],
        merged["category_id"],
        check_active=any(
            field in changes and changes[field] != getattr(tx, field)
            for field in ("account_id", "to_account_id", "category_id")
        ),
    )
    for field, value in changes.items():
        setattr(tx, field, value)
    await session.commit()
    return tx


async def delete_transaction(session: AsyncSession, member: LedgerMember, tx_id: int) -> None:
    tx = await get_transaction(session, member.ledger_id, tx_id)
    _ensure_can_edit(tx, member)
    tx.is_deleted = True  # мягкое удаление: остаток пересчитается, история сохранится
    await session.commit()
