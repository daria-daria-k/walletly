"""Применение обученных моделей и учёт A/B-теста."""

import math
import zlib
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml import anomaly as anomaly_model
from app.ml import categorizer
from app.ml import forecast as forecast_model
from app.ml.train import TASK_CATEGORIZER
from app.models import Account, Category, MlModel, MlSuggestion, Transaction
from app.models.enums import TransactionType
from app.services.errors import NotFoundError

MIN_CONFIDENCE = 0.5
_CACHE_SIZE = 64
_MIN_DECISIONS = 100  # меньше — разница между вариантами почти наверняка случайна
_SIGNIFICANCE = 0.05

_loaded: OrderedDict[int, object] = OrderedDict()


def variant_for(user_id: int) -> str:
    """Вариант зависит только от пользователя: один человек не должен видеть то одну модель, то другую."""
    return "B" if zlib.crc32(f"categorizer:{user_id}".encode()) % 2 else "A"


async def _predictor(session: AsyncSession, ledger_id: int, variant: str):
    row = (
        await session.execute(
            select(MlModel.id).where(
                MlModel.ledger_id == ledger_id,
                MlModel.task == TASK_CATEGORIZER,
                MlModel.variant == variant,
            )
        )
    ).first()
    if row is None:
        return None
    model_id = row[0]
    # id меняется при переобучении, поэтому устаревшая модель сама выпадает из кэша
    if model_id in _loaded:
        _loaded.move_to_end(model_id)
        return _loaded[model_id]
    payload = await session.scalar(select(MlModel.payload).where(MlModel.id == model_id))
    predictor = await run_in_threadpool(categorizer.load, variant, payload)
    _loaded[model_id] = predictor
    if len(_loaded) > _CACHE_SIZE:
        _loaded.popitem(last=False)
    return predictor


@dataclass(frozen=True)
class Suggestion:
    suggestion_id: int
    category_id: int
    confidence: float


async def _active_ids(session: AsyncSession, ledger_id: int) -> set[int]:
    rows = await session.scalars(
        select(Category.id).where(Category.ledger_id == ledger_id, Category.is_active.is_(True))
    )
    return set(rows)


async def suggest_category(
    session: AsyncSession, ledger_id: int, user_id: int, description: str
) -> Suggestion | None:
    variant = variant_for(user_id)
    predictor = await _predictor(session, ledger_id, variant)
    if predictor is None:
        return None
    category_id, confidence = (await run_in_threadpool(predictor, [description]))[0]
    # Модель могла выучить категорию, которую уже убрали в архив
    if confidence < MIN_CONFIDENCE or category_id not in await _active_ids(session, ledger_id):
        return None
    # Текст описания не сохраняем: для сравнения моделей он не нужен
    item = MlSuggestion(
        user_id=user_id,
        ledger_id=ledger_id,
        variant=variant,
        suggested_category_id=category_id,
        confidence=confidence,
    )
    session.add(item)
    await session.commit()
    return Suggestion(item.id, category_id, confidence)


async def record_outcome(
    session: AsyncSession, ledger_id: int, user_id: int, suggestion_id: int, category_id: int
) -> None:
    item = await session.scalar(
        select(MlSuggestion).where(
            MlSuggestion.id == suggestion_id,
            MlSuggestion.ledger_id == ledger_id,
            MlSuggestion.user_id == user_id,
        )
    )
    if item is None:
        raise NotFoundError("Подсказка не найдена")
    item.accepted = item.suggested_category_id == category_id
    await session.commit()


async def predict_for_import(
    session: AsyncSession, ledger_id: int, descriptions: list[str]
) -> dict[str, int]:
    """Импорт использует вариант A: у него нет отдельного человека, для которого идёт тест."""
    if not descriptions:
        return {}
    predictor = await _predictor(session, ledger_id, categorizer.VARIANT_SKLEARN)
    if predictor is None:
        return {}
    unique = list(dict.fromkeys(descriptions))
    predictions = await run_in_threadpool(predictor, unique)
    active = await _active_ids(session, ledger_id)
    return {
        text: category_id
        for text, (category_id, confidence) in zip(unique, predictions, strict=True)
        if confidence >= MIN_CONFIDENCE and category_id in active
    }


# --- Прогноз и аномалии ---


async def _expense_rows(session: AsyncSession, ledger_id: int, currency: str, since: date):
    return (
        await session.execute(
            select(Transaction.id, Transaction.tx_date, Transaction.amount, Transaction.category_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.ledger_id == ledger_id,
                Transaction.is_deleted.is_(False),
                Transaction.type == TransactionType.EXPENSE,
                Account.currency == currency,
                Transaction.tx_date >= since,
            )
        )
    ).all()


async def ml_forecast(
    session: AsyncSession, ledger_id: int, currency: str, today: date
) -> forecast_model.MlForecast | None:
    rows = await _expense_rows(session, ledger_id, currency, today - timedelta(days=760))
    points = [(row.tx_date, float(row.amount)) for row in rows if row.tx_date <= today]
    return await run_in_threadpool(forecast_model.predict, points, today)


async def ml_anomaly(
    session: AsyncSession, ledger_id: int, currency: str, today: date
) -> anomaly_model.Found | None:
    month_start = today.replace(day=1)
    rows = await _expense_rows(session, ledger_id, currency, today - timedelta(days=200))
    items = [
        anomaly_model.Row(row.id, row.category_id, float(row.amount), row.tx_date.weekday(), row.tx_date >= month_start)
        for row in rows
        if row.tx_date <= today
    ]
    return await run_in_threadpool(anomaly_model.find, items)


# --- A/B-тест ---


@dataclass(frozen=True)
class VariantStats:
    variant: str
    decided: int
    accepted: int
    accuracy: float | None


@dataclass(frozen=True)
class AbReport:
    variants: list[VariantStats]
    p_value: float | None
    winner: str | None


def two_proportion_p_value(a_ok: int, a_total: int, b_ok: int, b_total: int) -> float | None:
    """Вероятность увидеть такую разницу случайно, если модели на самом деле равны."""
    if not a_total or not b_total:
        return None
    pooled = (a_ok + b_ok) / (a_total + b_total)
    error = math.sqrt(pooled * (1 - pooled) * (1 / a_total + 1 / b_total))
    if error == 0:
        return 1.0
    z = abs(a_ok / a_total - b_ok / b_total) / error
    return math.erfc(z / math.sqrt(2))


async def ab_report(session: AsyncSession) -> AbReport:
    rows = dict(
        (variant, (decided, accepted))
        for variant, decided, accepted in await session.execute(
            select(
                MlSuggestion.variant,
                func.count(),
                func.count().filter(MlSuggestion.accepted.is_(True)),
            )
            .where(MlSuggestion.accepted.is_not(None))
            .group_by(MlSuggestion.variant)
        )
    )
    accuracy = dict((await session.execute(select(MlModel.variant, func.avg(MlModel.accuracy)).group_by(MlModel.variant))).all())
    variants = [
        VariantStats(name, *rows.get(name, (0, 0)), accuracy.get(name)) for name in ("A", "B")
    ]
    a, b = variants
    p_value = two_proportion_p_value(a.accepted, a.decided, b.accepted, b.decided)
    winner = None
    if (
        p_value is not None
        and p_value < _SIGNIFICANCE
        and min(a.decided, b.decided) >= _MIN_DECISIONS
    ):
        winner = "A" if a.accepted / a.decided > b.accepted / b.decided else "B"
    return AbReport(variants, p_value, winner)
