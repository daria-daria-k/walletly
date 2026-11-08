from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.errors import NotFoundError

T = TypeVar("T")


async def get_in_ledger(session: AsyncSession, model: type[T], ledger_id: int, obj_id: int) -> T:
    """Ищет объект только внутри пространства.

    Без условия по ledger_id участник своего пространства мог бы подставить
    чужой id в URL и прочитать или изменить чужие данные.
    """
    obj = await session.scalar(
        select(model).where(model.id == obj_id, model.ledger_id == ledger_id)  # type: ignore[attr-defined]
    )
    if obj is None:
        raise NotFoundError("Объект не найден")
    return obj
