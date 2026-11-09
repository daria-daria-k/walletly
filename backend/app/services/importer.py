from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Account, Category, CategoryGroup, ImportBatch, LedgerMember, Transaction
from app.models.enums import CategoryType, Plan, TransactionType
from app.schemas.imports import ImportResult, ImportRowError
from app.services import file_sandbox, statement
from app.services.billing import get_plan
from app.services.errors import DomainError, InvalidDataError
from app.services.ml import predict_for_import
from app.services.scoped import get_in_ledger
from app.services.transaction import check_fields

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_AMOUNT = Decimal("9999999999.99")  # предел NUMERIC(12, 2)

_COLUMNS = {
    "дата": "date",
    "тип": "type",
    "сумма": "amount",
    "счёт": "account",
    "счет": "account",
    "счёт зачисления": "to_account",
    "счет зачисления": "to_account",
    "категория": "category",
    "описание": "description",
}
_REQUIRED = {"date", "amount", "account"}
_TYPES = {
    "доход": TransactionType.INCOME,
    "расход": TransactionType.EXPENSE,
    "перевод": TransactionType.TRANSFER,
}
_DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y")


@dataclass(frozen=True)
class ParsedRow:
    number: int
    values: dict[str, object]


async def _parse_table(content: bytes, filename: str) -> list[ParsedRow]:
    kind = "csv" if filename.lower().endswith(".csv") else "xlsx"
    table = (await file_sandbox.run(kind, content))["rows"]

    if not table:
        raise InvalidDataError("Файл пустой")
    header = [_COLUMNS.get(str(cell or "").strip().lower()) for cell in table[0][1]]
    missing = _REQUIRED - set(header)
    if missing:
        raise InvalidDataError("В файле нет обязательных колонок: Дата, Сумма, Счёт")
    return [
        ParsedRow(
            number,
            {name: cell for name, cell in zip(header, cells, strict=False) if name is not None},
        )
        for number, cells in table[1:]
    ]


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(_text(value), fmt).date()
        except ValueError:
            continue
    raise InvalidDataError("Неверная дата, ожидается ДД.ММ.ГГГГ")


def _parse_amount(value: object) -> Decimal:
    # Через str и для чисел из Excel: Decimal(0.1) сохранил бы двоичную погрешность float
    raw = _text(value).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise InvalidDataError("Неверная сумма") from None
    if not amount.is_finite() or amount == 0 or abs(amount) > MAX_AMOUNT:
        raise InvalidDataError("Неверная сумма")
    if amount != amount.quantize(Decimal("0.01")):
        raise InvalidDataError("В сумме больше двух знаков после запятой")
    return amount.quantize(Decimal("0.01"))


class _Lookup:
    """Поиск счетов и категорий по названию без регистра — без запроса на каждую строку."""

    def __init__(self, accounts: list[Account], categories: list[Category]) -> None:
        self.accounts: dict[str, list[Account]] = {}
        for account in accounts:
            self.accounts.setdefault(account.name.casefold(), []).append(account)
        self.categories: dict[tuple[str, CategoryType], list[Category]] = {}
        self.by_id = {category.id: category for category in categories}
        for category in categories:
            key = (category.name.casefold(), category.group.type)
            self.categories.setdefault(key, []).append(category)

    def account(self, name: str) -> Account:
        found = self.accounts.get(name.casefold(), [])
        if not found:
            raise InvalidDataError(f"Счёт «{name}» не найден")
        if len(found) > 1:
            raise InvalidDataError(f"Несколько счетов с названием «{name}»")
        return found[0]

    def category(self, name: str, tx_type: TransactionType) -> Category:
        kind = CategoryType.INCOME if tx_type == TransactionType.INCOME else CategoryType.EXPENSE
        found = self.categories.get((name.casefold(), kind), [])
        if not found:
            raise InvalidDataError(f"Категория «{name}» не найдена")
        if len(found) > 1:
            raise InvalidDataError(f"Несколько категорий с названием «{name}»")
        return found[0]


def _predicted_category(
    description: str,
    tx_type: TransactionType,
    lookup: _Lookup,
    predicted: dict[str, int],
    fallback: dict[CategoryType, int],
) -> Category | None:
    if tx_type == TransactionType.TRANSFER:
        return None
    wanted = CategoryType.INCOME if tx_type == TransactionType.INCOME else CategoryType.EXPENSE
    category = lookup.by_id.get(predicted.get(description, 0))
    # Доход нельзя отнести к категории расходов, даже если модель так решила
    if category is not None and category.group.type == wanted:
        return category
    return lookup.by_id.get(fallback.get(wanted, 0))


def _build(
    row: ParsedRow,
    lookup: _Lookup,
    member: LedgerMember,
    predicted: dict[str, int],
    fallback: dict[CategoryType, int],
) -> Transaction:
    values = row.values
    tx_date = _parse_date(values.get("date"))
    amount = _parse_amount(values.get("amount"))

    type_text = _text(values.get("type")).lower()
    if type_text:
        tx_type = _TYPES.get(type_text)
        if tx_type is None:
            raise InvalidDataError("Тип: доход, расход или перевод")
    else:
        # В выписках тип часто не указан: его задаёт знак суммы
        tx_type = TransactionType.EXPENSE if amount < 0 else TransactionType.INCOME

    account = lookup.account(_text(values.get("account")))
    to_name = _text(values.get("to_account"))
    to_account = lookup.account(to_name) if to_name else None
    category_name = _text(values.get("category"))
    description = _text(values.get("description"))
    category = (
        lookup.category(category_name, tx_type)
        if category_name
        else _predicted_category(description, tx_type, lookup, predicted, fallback)
    )
    check_fields(tx_type, account, to_account, category, check_active=True)

    if len(description) > 500:
        raise InvalidDataError("Описание длиннее 500 символов")

    return Transaction(
        ledger_id=member.ledger_id,
        user_id=member.user_id,
        type=tx_type,
        amount=abs(amount),
        account_id=account.id,
        to_account_id=to_account.id if to_account else None,
        category_id=category.id if category else None,
        description=description or None,
        tx_date=tx_date,
    )


def _fingerprint(tx: Transaction) -> tuple:
    return (
        tx.tx_date,
        tx.type,
        tx.amount,
        tx.account_id,
        tx.to_account_id,
        tx.category_id,
        tx.description or "",
    )


async def import_transactions(
    session: AsyncSession, member: LedgerMember, content: bytes, filename: str, *, dry_run: bool
) -> ImportResult:
    rows = await _parse_table(content, filename)
    return await _import_rows(session, member, rows, filename, dry_run=dry_run)


async def _fallback_categories(session: AsyncSession, ledger_id: int) -> dict[CategoryType, int]:
    """Для выписки: в банковском файле нет категорий, а терять строки нельзя."""
    result: dict[CategoryType, int] = {}
    names = {CategoryType.EXPENSE: "Прочие расходы", CategoryType.INCOME: "Прочие доходы"}
    for kind, name in names.items():
        group = await session.scalar(
            select(CategoryGroup)
            .where(CategoryGroup.ledger_id == ledger_id, CategoryGroup.type == kind)
            .order_by(CategoryGroup.sort_order.desc(), CategoryGroup.id.desc())
            .limit(1)
        )
        if group is None:
            continue
        category = await session.scalar(
            select(Category).where(Category.ledger_id == ledger_id, Category.name == name)
        )
        if category is None:
            category = Category(ledger_id=ledger_id, category_group_id=group.id, name=name)
            session.add(category)
            await session.flush()
        result[kind] = category.id
    await session.commit()
    return result


async def import_statement(
    session: AsyncSession,
    member: LedgerMember,
    content: bytes,
    filename: str,
    account_id: int,
    *,
    dry_run: bool,
) -> ImportResult:
    account = await get_in_ledger(session, Account, member.ledger_id, account_id)
    text = (await file_sandbox.run("pdf", content))["text"]
    lines = statement.parse_text(text)
    if not lines:
        raise InvalidDataError("В файле не найдено операций. Возможно, это скан или другой формат")
    rows = [
        ParsedRow(
            number,
            {
                "date": line.tx_date,
                "amount": str(line.amount),
                "account": account.name,
                "description": line.description,
            },
        )
        for number, line in enumerate(lines, start=1)
    ]
    fallback = await _fallback_categories(session, member.ledger_id)
    return await _import_rows(session, member, rows, filename, dry_run=dry_run, fallback=fallback)


async def _import_rows(
    session: AsyncSession,
    member: LedgerMember,
    rows: list[ParsedRow],
    filename: str,
    *,
    dry_run: bool,
    fallback: dict[CategoryType, int] | None = None,
) -> ImportResult:
    accounts = await session.scalars(
        select(Account).where(Account.ledger_id == member.ledger_id)
    )
    categories = await session.scalars(
        select(Category)
        .options(joinedload(Category.group))
        .where(Category.ledger_id == member.ledger_id)
    )
    lookup = _Lookup(list(accounts), list(categories))

    predicted: dict[str, int] = {}
    if await get_plan(session, member.user_id) == Plan.PREMIUM:
        predicted = await predict_for_import(
            session,
            member.ledger_id,
            [
                _text(row.values.get("description"))
                for row in rows
                if not _text(row.values.get("category")) and _text(row.values.get("description"))
            ],
        )

    built: list[Transaction] = []
    errors: list[ImportRowError] = []
    for row in rows:
        try:
            built.append(_build(row, lookup, member, predicted, fallback or {}))
        except DomainError as exc:
            errors.append(ImportRowError(row=row.number, message=exc.message))

    new, skipped = await _drop_duplicates(session, member.ledger_id, built)

    # Всё или ничего: иначе после исправления файла половина строк загрузилась бы дважды
    created = len(new) if not errors else 0
    if created and not dry_run:
        session.add_all(new)
    # В историю идут настоящие загрузки и файлы с ошибками, а успешная проверка ещё ничего не изменила
    if errors or (created and not dry_run):
        session.add(
            ImportBatch(
                ledger_id=member.ledger_id,
                filename=filename[:255],
                total_rows=len(rows),
                created=created,
                skipped_duplicates=skipped,
                errors=len(errors),
            )
        )
        await session.commit()

    return ImportResult(
        total_rows=len(rows),
        created=created,
        skipped_duplicates=skipped,
        errors=errors,
        dry_run=dry_run,
    )


async def _drop_duplicates(
    session: AsyncSession, ledger_id: int, built: list[Transaction]
) -> tuple[list[Transaction], int]:
    """Повторная загрузка того же файла не должна удваивать операции.

    Сравниваем как мультимножества: два одинаковых кофе в первой загрузке — это две
    настоящие покупки, а вот при повторе обе уже есть в базе и будут пропущены.
    """
    if not built:
        return [], 0
    existing = await session.scalars(
        select(Transaction).where(
            Transaction.ledger_id == ledger_id,
            Transaction.is_deleted.is_(False),
            Transaction.tx_date >= min(tx.tx_date for tx in built),
            Transaction.tx_date <= max(tx.tx_date for tx in built),
        )
    )
    remaining = Counter(_fingerprint(tx) for tx in existing)
    new: list[Transaction] = []
    skipped = 0
    for tx in built:
        key = _fingerprint(tx)
        if remaining[key] > 0:
            remaining[key] -= 1
            skipped += 1
        else:
            new.append(tx)
    return new, skipped


async def import_history(
    session: AsyncSession, ledger_id: int, limit: int = 10
) -> list[ImportBatch]:
    batches = await session.scalars(
        select(ImportBatch)
        .where(ImportBatch.ledger_id == ledger_id)
        .order_by(ImportBatch.id.desc())
        .limit(limit)
    )
    return list(batches)
