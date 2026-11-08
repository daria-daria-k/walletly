from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subscription, Transaction, User
from app.models.enums import Plan
from app.schemas.admin import AdminStats, AdminUserRead, AdminUserUpdate
from app.services.auth import revoke_all_refresh_tokens
from app.services.errors import ConflictError, NotFoundError

# Действующий тариф — последняя запись подписки: старые остаются как история
_current_plan = (
    select(Subscription.plan)
    .where(Subscription.user_id == User.id)
    .order_by(Subscription.id.desc())
    .limit(1)
    .correlate(User)
    .scalar_subquery()
)


def _to_read(user: User, plan: Plan) -> AdminUserRead:
    return AdminUserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        plan=plan,
        created_at=user.created_at,
    )


async def stats(session: AsyncSession) -> AdminStats:
    users_total = await session.scalar(select(func.count()).select_from(User))
    users_active = await session.scalar(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    )
    users_premium = await session.scalar(
        select(func.count()).select_from(User).where(_current_plan == Plan.PREMIUM)
    )
    transactions = await session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.is_deleted.is_(False))
    )
    return AdminStats(
        users_total=users_total,
        users_active=users_active,
        users_premium=users_premium,
        transactions_total=transactions,
    )


async def list_users(
    session: AsyncSession, search: str | None, limit: int, offset: int
) -> tuple[list[AdminUserRead], int]:
    condition = True
    if search:
        condition = or_(
            User.email.icontains(search, autoescape=True),
            User.name.icontains(search, autoescape=True),
        )
    total = await session.scalar(select(func.count()).select_from(User).where(condition))
    rows = await session.execute(
        select(User, _current_plan).where(condition).order_by(User.id).limit(limit).offset(offset)
    )
    return [_to_read(user, plan) for user, plan in rows], total


async def update_user(
    session: AsyncSession, actor: User, user_id: int, data: AdminUserUpdate
) -> AdminUserRead:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    changes = data.model_dump(exclude_unset=True)

    # Защита от случайной потери доступа: иначе последний администратор может запереть себя
    if user.id == actor.id and ("is_active" in changes or "role" in changes):
        raise ConflictError("Нельзя менять собственный статус или роль")

    if "is_active" in changes:
        user.is_active = changes["is_active"]
        if not user.is_active:
            # get_current_user остановит запросы сразу, а отзыв закрывает и refresh
            await revoke_all_refresh_tokens(session, user.id)
    if "role" in changes:
        user.role = changes["role"]
    if "plan" in changes:
        session.add(Subscription(user_id=user.id, plan=changes["plan"]))

    await session.commit()
    plan = await session.scalar(select(_current_plan).select_from(User).where(User.id == user.id))
    return _to_read(user, plan)
