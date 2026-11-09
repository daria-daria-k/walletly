"""Обучение моделей: python -m app.ml.train (по расписанию запускает worker)."""

import asyncio
import logging

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.ml import categorizer
from app.models import Ledger, MlModel, Transaction
from app.models.enums import Plan, TransactionType
from app.services.billing import get_plan

logger = logging.getLogger("walletly.ml")

_MAX_ROWS = 5000
TASK_CATEGORIZER = "categorizer"


def _log_to_mlflow(ledger_id: int, variant: str, result: categorizer.Trained) -> None:
    """Только числа: описания операций — личные данные, в сервис экспериментов они не уходят."""
    if not settings.mlflow_tracking_uri:
        return
    import mlflow  # импорт здесь: API он не нужен, а запускается долго

    try:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment("walletly-categorizer")
        with mlflow.start_run(run_name=f"ledger-{ledger_id}-{variant}"):
            mlflow.log_params({"ledger_id": ledger_id, "variant": variant})
            mlflow.log_metrics(
                {"accuracy": result.accuracy, "samples": result.samples, "classes": result.classes}
            )
    except Exception:  # noqa: BLE001 — падение журнала не должно ломать обучение
        logger.exception("MLflow недоступен, метрики не записаны")


async def train_ledger(session: AsyncSession, ledger_id: int) -> dict[str, categorizer.Trained]:
    rows = (
        await session.execute(
            select(Transaction.description, Transaction.category_id)
            .where(
                Transaction.ledger_id == ledger_id,
                Transaction.is_deleted.is_(False),
                Transaction.type != TransactionType.TRANSFER,
                Transaction.description.is_not(None),
            )
            .order_by(Transaction.id.desc())
            .limit(_MAX_ROWS)
        )
    ).all()
    data = categorizer.prepare([row[0] for row in rows], [row[1] for row in rows])
    if data is None:
        return {}

    results: dict[str, categorizer.Trained] = {}
    for variant, trainer in categorizer.TRAINERS.items():
        # В отдельном потоке: обучение занимает секунды, а планировщик должен жить дальше
        results[variant] = await run_in_threadpool(trainer, data)

    await session.execute(
        delete(MlModel).where(MlModel.ledger_id == ledger_id, MlModel.task == TASK_CATEGORIZER)
    )
    session.add_all(
        MlModel(
            ledger_id=ledger_id,
            task=TASK_CATEGORIZER,
            variant=variant,
            payload=result.payload,
            accuracy=result.accuracy,
            samples=result.samples,
        )
        for variant, result in results.items()
    )
    await session.commit()
    for variant, result in results.items():
        await run_in_threadpool(_log_to_mlflow, ledger_id, variant, result)
    return results


async def train_all() -> int:
    async with SessionLocal() as session:
        ledgers = (await session.execute(select(Ledger.id, Ledger.owner_id))).all()
        trained = 0
        for ledger_id, owner_id in ledgers:
            # Обучение стоит процессорного времени, а функция входит только в Premium
            if await get_plan(session, owner_id) != Plan.PREMIUM:
                continue
            if await train_ledger(session, ledger_id):
                trained += 1
    return trained


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    print(f"Обучено пространств: {await train_all()}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
