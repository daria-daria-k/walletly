import io
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi.concurrency import run_in_threadpool
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Transaction
from app.models.enums import TransactionType

_TYPE_LABEL = {
    TransactionType.INCOME: "доход",
    TransactionType.EXPENSE: "расход",
    TransactionType.TRANSFER: "перевод",
}
_FORMULA_START = ("=", "+", "-", "@")


def _append(sheet, values: list) -> None:
    sheet.append(values)
    for cell in sheet[sheet.max_row]:
        # Описание пишет пользователь или банк: «=HYPERLINK(...)» Excel выполнил бы как формулу.
        # Тип «строка» показывает текст как есть и не меняет его, в отличие от апострофа
        if isinstance(cell.value, str) and cell.value.startswith(_FORMULA_START):
            cell.data_type = "s"


def _build_workbook(transactions: list[Transaction]) -> bytes:
    book = Workbook()
    operations = book.active
    operations.title = "Операции"
    # Те же колонки, что у импорта: выгрузку можно загрузить обратно
    _append(operations, ["Дата", "Тип", "Сумма", "Счёт", "Счёт зачисления", "Категория", "Описание"])

    totals: dict[str, dict[TransactionType, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for tx in transactions:
        _append(
            operations,
            [
                tx.tx_date,
                _TYPE_LABEL[tx.type],
                tx.amount,
                tx.account.name,
                tx.to_account.name if tx.to_account else None,
                tx.category.name if tx.category else None,
                tx.description,
            ],
        )
        totals[tx.account.currency][tx.type] += tx.amount

    summary = book.create_sheet("Сводка")
    _append(summary, ["Валюта", "Доходы", "Расходы", "Разница"])
    for currency, by_type in sorted(totals.items()):
        income = by_type[TransactionType.INCOME]
        expense = by_type[TransactionType.EXPENSE]
        _append(summary, [currency, income, expense, income - expense])

    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


async def export_xlsx(
    session: AsyncSession, ledger_id: int, date_from: date | None, date_to: date | None
) -> bytes:
    query = (
        select(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.to_account),
            joinedload(Transaction.category),
        )
        .where(Transaction.ledger_id == ledger_id, Transaction.is_deleted.is_(False))
        .order_by(Transaction.tx_date, Transaction.id)
    )
    if date_from:
        query = query.where(Transaction.tx_date >= date_from)
    if date_to:
        query = query.where(Transaction.tx_date <= date_to)
    transactions = list(await session.scalars(query))
    # Сборка файла — работа CPU, в event loop она остановила бы все запросы
    return await run_in_threadpool(_build_workbook, transactions)
