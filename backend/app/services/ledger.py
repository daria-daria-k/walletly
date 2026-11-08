from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Account, Category, CategoryGroup, Ledger, LedgerMember, Transaction, User
from app.models.enums import LedgerType, MemberRole
from app.services.category_template import DEFAULT_CATEGORY_GROUPS
from app.services.errors import ConflictError, NotFoundError, PermissionDeniedError


async def add_default_categories(session: AsyncSession, ledger_id: int) -> None:
    """Копирует шаблон категорий в пространство. Коммит — на вызывающем коде."""
    for group_order, (group_name, category_type, category_names) in enumerate(
        DEFAULT_CATEGORY_GROUPS
    ):
        group = CategoryGroup(
            ledger_id=ledger_id, name=group_name, type=category_type, sort_order=group_order
        )
        group.categories = [
            Category(ledger_id=ledger_id, name=name, sort_order=order)
            for order, name in enumerate(category_names)
        ]
        session.add(group)


async def list_user_ledgers(session: AsyncSession, user_id: int) -> list[LedgerMember]:
    result = await session.scalars(
        select(LedgerMember)
        .options(joinedload(LedgerMember.ledger))
        .where(LedgerMember.user_id == user_id)
        .order_by(LedgerMember.ledger_id)
    )
    return list(result)


async def create_shared_ledger(session: AsyncSession, user: User, name: str) -> LedgerMember:
    ledger = Ledger(name=name, type=LedgerType.SHARED, owner=user)
    member = LedgerMember(ledger=ledger, user=user, role=MemberRole.OWNER)
    session.add_all([ledger, member])
    await session.flush()  # нужен ledger.id для категорий
    await add_default_categories(session, ledger.id)
    await session.commit()
    return member


async def rename_ledger(session: AsyncSession, ledger: Ledger, name: str) -> None:
    ledger.name = name
    await session.commit()


async def delete_ledger(session: AsyncSession, ledger: Ledger) -> None:
    if ledger.type == LedgerType.PERSONAL:
        raise ConflictError("Личное пространство удалить нельзя")
    # Порядок важен: у transactions и categories внешние ключи с RESTRICT, и одного
    # каскада от ledgers не хватит — БД откажет, если дойдёт до счёта раньше операций
    for model in (Transaction, Category, CategoryGroup, Account):
        await session.execute(delete(model).where(model.ledger_id == ledger.id))
    # Прямой DELETE, а не session.delete: ORM попытался бы занулить ledger_id у участников,
    # тогда как их и приглашения удалит каскад в самой БД
    await session.execute(delete(Ledger).where(Ledger.id == ledger.id))
    await session.commit()


async def list_members(session: AsyncSession, ledger_id: int) -> list[LedgerMember]:
    result = await session.scalars(
        select(LedgerMember)
        .options(joinedload(LedgerMember.user))
        .where(LedgerMember.ledger_id == ledger_id)
        .order_by(LedgerMember.joined_at, LedgerMember.id)
    )
    return list(result)


async def _get_member(session: AsyncSession, ledger_id: int, user_id: int) -> LedgerMember:
    member = await session.scalar(
        select(LedgerMember)
        .options(joinedload(LedgerMember.user))
        .where(LedgerMember.ledger_id == ledger_id, LedgerMember.user_id == user_id)
    )
    if member is None:
        raise NotFoundError("Участник не найден")
    return member


async def change_member_role(
    session: AsyncSession, actor: LedgerMember, user_id: int, role: MemberRole
) -> LedgerMember:
    if actor.role != MemberRole.OWNER:
        raise PermissionDeniedError("Менять роли может только владелец")
    if role == MemberRole.OWNER:
        raise ConflictError("Передача владения пока не поддерживается")
    target = await _get_member(session, actor.ledger_id, user_id)
    if target.role == MemberRole.OWNER:
        raise ConflictError("Роль владельца изменить нельзя")
    target.role = role
    await session.commit()
    return target


async def remove_member(session: AsyncSession, actor: LedgerMember, user_id: int) -> None:
    """Исключение участника или выход из пространства, если user_id — свой."""
    target = await _get_member(session, actor.ledger_id, user_id)
    if target.role == MemberRole.OWNER:
        raise ConflictError("Владельца нельзя исключить из пространства")
    is_self = target.user_id == actor.user_id
    if not is_self:
        if actor.role == MemberRole.MEMBER:
            raise PermissionDeniedError("Нужны права владельца или администратора")
        if actor.role == MemberRole.ADMIN and target.role == MemberRole.ADMIN:
            raise PermissionDeniedError("Администратора может исключить только владелец")
    # Операции ушедшего участника остаются: это общая история пространства
    await session.delete(target)
    await session.commit()
