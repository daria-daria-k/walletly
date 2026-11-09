"""Подсказки на правилах и статистике. Модели машинного обучения появятся на этапе 4."""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Transaction
from app.models.enums import TransactionType
from app.schemas.insights import Anomaly, Forecast, Insights, LimitsStatus, Overspend, PlanItem
from app.services.analytics import scoped_transactions

_HISTORY_MONTHS = 3
_ANOMALY_MONTHS = 6
_ANOMALY_MIN_OPERATIONS = 3  # по одной-двум операциям «обычная сумма» ещё не определена
_ANOMALY_RATIO = Decimal(3)
_OVERSPEND_SHARE = Decimal("0.1")  # мелкие колебания подсказкой не считаем
_LIMIT_WARNING = Decimal("0.8")
_PLAN_SIZE = 3


def _months_back(month_start: date, count: int) -> date:
    index = month_start.year * 12 + month_start.month - 1 - count
    return date(index // 12, index % 12 + 1, 1)


async def _month_totals(
    session: AsyncSession, ledger_id: int, currency: str, start: date, today: date
) -> tuple[dict[int, Decimal], dict[int, Decimal], int]:
    """Расходы по категориям: за текущий месяц и сумма за прошлые, плюс число прошлых месяцев."""
    month = func.to_char(Transaction.tx_date, "YYYY-MM")
    rows = await session.execute(
        scoped_transactions(
            select(Transaction.category_id, month, func.sum(Transaction.amount))
            .where(Transaction.type == TransactionType.EXPENSE)
            .group_by(Transaction.category_id, month),
            ledger_id,
            currency,
            start,
            today,
        )
    )
    current_key = today.strftime("%Y-%m")
    current: dict[int, Decimal] = {}
    past: dict[int, Decimal] = {}
    past_months: set[str] = set()
    for category_id, key, total in rows:
        if key == current_key:
            current[category_id] = total
        else:
            past[category_id] = past.get(category_id, Decimal(0)) + total
            past_months.add(key)
    return current, past, len(past_months)


async def _find_anomaly(
    session: AsyncSession,
    ledger_id: int,
    currency: str,
    month_start: date,
    today: date,
    names: dict[int, str],
) -> Anomaly | None:
    usual = await session.execute(
        scoped_transactions(
            select(Transaction.category_id, func.avg(Transaction.amount))
            .where(Transaction.type == TransactionType.EXPENSE)
            .group_by(Transaction.category_id)
            .having(func.count() >= _ANOMALY_MIN_OPERATIONS),
            ledger_id,
            currency,
            _months_back(month_start, _ANOMALY_MONTHS),
            month_start - timedelta(days=1),
        )
    )
    average = dict(usual.all())
    if not average:
        return None
    transactions = await session.scalars(
        scoped_transactions(
            select(Transaction).where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.category_id.in_(average),
            ),
            ledger_id,
            currency,
            month_start,
            today,
        )
    )
    best: Anomaly | None = None
    for tx in transactions:
        ratio = (tx.amount / average[tx.category_id]).quantize(Decimal("0.1"))
        if ratio >= _ANOMALY_RATIO and (best is None or ratio > best.ratio):
            category_name = names.get(tx.category_id, "")
            best = Anomaly(
                transaction_id=tx.id,
                title=tx.description or category_name,
                category_name=category_name,
                amount=tx.amount,
                ratio=ratio,
                tx_date=tx.tx_date,
            )
    return best


async def build_insights(
    session: AsyncSession, ledger_id: int, currency: str, today: date | None = None
) -> Insights:
    today = today or date.today()
    month_start = today.replace(day=1)
    progress = Decimal(today.day) / monthrange(today.year, today.month)[1]

    current, past, months = await _month_totals(
        session, ledger_id, currency, _months_back(month_start, _HISTORY_MONTHS), today
    )
    baseline = {key: value / months for key, value in past.items()} if months else {}
    categories = list(await session.scalars(select(Category).where(Category.ledger_id == ledger_id)))
    names = {category.id: category.name for category in categories}

    spent = sum(current.values(), Decimal(0))
    baseline_total = sum(baseline.values(), Decimal(0)) if baseline else None
    # Та же линейная оценка, что и на экране аналитики: цифры на экранах не должны расходиться
    projected = (spent / progress).quantize(Decimal("0.01"))
    change = (
        round((projected - baseline_total) / baseline_total * 100) if baseline_total else None
    )

    # Сравниваем с долей месяца: иначе 1-го числа любая покупка кажется нормой, а 30-го превышением
    overspending = {
        key: value - baseline[key] * progress
        for key, value in current.items()
        if baseline.get(key) and value - baseline[key] * progress >= baseline[key] * _OVERSPEND_SHARE
    }
    top = max(overspending, key=overspending.__getitem__, default=None)

    with_limit = [c for c in categories if c.monthly_limit and c.is_active]
    shares = [current.get(c.id, Decimal(0)) / c.monthly_limit for c in with_limit]

    weight = {key: baseline.get(key) or current.get(key, Decimal(0)) for key in {*baseline, *current}}
    leaders = sorted(weight, key=weight.__getitem__, reverse=True)[:_PLAN_SIZE]
    limited = {c.id for c in with_limit}

    return Insights(
        forecast=Forecast(
            spent=spent,
            projected=projected,
            baseline=round(baseline_total, 2) if baseline_total else None,
            change_percent=change,
            month_progress=round(progress * 100),
        ),
        anomaly=await _find_anomaly(session, ledger_id, currency, month_start, today, names),
        overspend=Overspend(
            category_id=top, category_name=names[top], amount=round(overspending[top], 2)
        )
        if top is not None
        else None,
        limits=LimitsStatus(
            total=len(with_limit),
            near=sum(_LIMIT_WARNING <= share < 1 for share in shares),
            over=sum(share >= 1 for share in shares),
        ),
        plan=[
            PlanItem(
                category_id=key,
                category_name=names[key],
                average=round(weight[key], 2),
                has_limit=key in limited,
            )
            for key in leaders
        ],
        potential=round(sum(overspending.values(), Decimal(0)), 2),
    )
