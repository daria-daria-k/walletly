from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Category, CategoryGroup
from app.schemas.category import (
    CategoryCreate,
    CategoryGroupCreate,
    CategoryGroupUpdate,
    CategoryUpdate,
)
from app.services.errors import ConflictError, InvalidDataError
from app.services.scoped import get_in_ledger


async def list_groups(session: AsyncSession, ledger_id: int) -> list[CategoryGroup]:
    result = await session.scalars(
        select(CategoryGroup)
        # selectinload: категории подгружаются вторым запросом сразу для всех групп (без N+1)
        .options(selectinload(CategoryGroup.categories))
        .where(CategoryGroup.ledger_id == ledger_id)
        .order_by(CategoryGroup.sort_order, CategoryGroup.id)
    )
    groups = list(result)
    for group in groups:
        group.categories.sort(key=lambda c: (c.sort_order, c.id))
    return groups


async def create_group(
    session: AsyncSession, ledger_id: int, data: CategoryGroupCreate
) -> CategoryGroup:
    group = CategoryGroup(ledger_id=ledger_id, categories=[], **data.model_dump())
    session.add(group)
    await session.commit()
    return group


async def update_group(
    session: AsyncSession, ledger_id: int, group_id: int, data: CategoryGroupUpdate
) -> CategoryGroup:
    group = await get_in_ledger(session, CategoryGroup, ledger_id, group_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(group, field, value)
    await session.commit()
    await session.refresh(group, ["categories"])
    return group


async def delete_group(session: AsyncSession, ledger_id: int, group_id: int) -> None:
    group = await get_in_ledger(session, CategoryGroup, ledger_id, group_id)
    has_categories = await session.scalar(
        select(Category.id).where(Category.category_group_id == group.id).limit(1)
    )
    if has_categories:
        raise ConflictError("В группе есть категории — сначала перенесите или удалите их")
    await session.delete(group)
    await session.commit()


async def _commit_category(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError("Категория с таким названием уже есть в этой группе") from None


async def create_category(session: AsyncSession, ledger_id: int, data: CategoryCreate) -> Category:
    await get_in_ledger(session, CategoryGroup, ledger_id, data.category_group_id)
    category = Category(ledger_id=ledger_id, **data.model_dump())
    session.add(category)
    await _commit_category(session)
    return category


async def update_category(
    session: AsyncSession, ledger_id: int, category_id: int, data: CategoryUpdate
) -> Category:
    category = await get_in_ledger(session, Category, ledger_id, category_id)
    changes = data.model_dump(exclude_unset=True)

    new_group_id = changes.get("category_group_id")
    if new_group_id is not None and new_group_id != category.category_group_id:
        current = await get_in_ledger(
            session, CategoryGroup, ledger_id, category.category_group_id
        )
        target = await get_in_ledger(session, CategoryGroup, ledger_id, new_group_id)
        # Тип наследуется от группы: перенос в группу другого типа сделал бы
        # уже записанные операции несовместимыми со своей категорией
        if target.type != current.type:
            raise InvalidDataError("Нельзя перенести категорию в группу другого типа")

    for field, value in changes.items():
        setattr(category, field, value)
    await _commit_category(session)
    return category


async def delete_category(session: AsyncSession, ledger_id: int, category_id: int) -> None:
    category = await get_in_ledger(session, Category, ledger_id, category_id)
    await session.delete(category)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError("По категории есть операции — её можно только архивировать") from None
