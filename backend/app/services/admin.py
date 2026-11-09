from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditEntry, Subscription, Transaction, User
from app.models.enums import Plan
from app.schemas.admin import AdminStats, AdminUserRead, AdminUserUpdate, WeekCount
from app.services.auth import revoke_all_refresh_tokens
from app.services.errors import ConflictError, NotFoundError

# Действующий тариф — последняя запись подписки: старые остаются как история
_current_plan = (
    select(Subscription.plan)
    .where(
        Subscription.user_id == User.id,
        or_(Subscription.expires_at.is_(None), Subscription.expires_at > func.now()),
    )
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


async def _registrations_by_week(session: AsyncSession, weeks: int = 8) -> list[WeekCount]:
    today = datetime.now(UTC).date()
    this_week = today - timedelta(days=today.weekday())
    first = this_week - timedelta(weeks=weeks - 1)
    week = func.date_trunc("week", User.created_at)
    rows = await session.execute(
        select(week, func.count()).where(User.created_at >= first).group_by(week)
    )
    counts = {started.date(): count for started, count in rows}
    # Недели без регистраций тоже нужны: иначе на графике время сожмётся
    return [
        WeekCount(week_start=day, count=counts.get(day, 0))
        for day in (first + timedelta(weeks=n) for n in range(weeks))
    ]


async def stats(session: AsyncSession) -> AdminStats:
    users_total = await session.scalar(select(func.count()).select_from(User))
    users_active = await session.scalar(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    )
    users_premium = await session.scalar(
        select(func.count()).select_from(User).where(_current_plan == Plan.PREMIUM)
    )
    users_new = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.created_at >= datetime.now(UTC) - timedelta(days=30))
    )
    transactions = await session.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.is_deleted.is_(False))
    )
    return AdminStats(
        users_total=users_total,
        users_active=users_active,
        users_premium=users_premium,
        users_new_30d=users_new,
        transactions_total=transactions,
        registrations=await _registrations_by_week(session),
    )


async def list_users(
    session: AsyncSession, search: str | None, plan: Plan | None, limit: int, offset: int
) -> tuple[list[AdminUserRead], int]:
    conditions = []
    if search:
        conditions.append(
            or_(
                User.email.icontains(search, autoescape=True),
                User.name.icontains(search, autoescape=True),
            )
        )
    if plan:
        conditions.append(_current_plan == plan)
    total = await session.scalar(select(func.count()).select_from(User).where(*conditions))
    rows = await session.execute(
        select(User, _current_plan).where(*conditions).order_by(User.id).limit(limit).offset(offset)
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

    def audit(action: str, detail: str) -> None:
        # В одной транзакции с изменением: не будет ни правки без записи, ни записи без правки
        session.add(
            AdminAuditEntry(
                actor_email=actor.email, target_email=user.email, action=action, detail=detail
            )
        )

    if "is_active" in changes and changes["is_active"] != user.is_active:
        user.is_active = changes["is_active"]
        audit("status", "Разблокирован" if user.is_active else "Заблокирован")
        if not user.is_active:
            # get_current_user остановит запросы сразу, а отзыв закрывает и refresh
            await revoke_all_refresh_tokens(session, user.id)
    if "role" in changes and changes["role"] != user.role:
        user.role = changes["role"]
        audit("role", user.role.value)
    if "plan" in changes:
        session.add(Subscription(user_id=user.id, plan=changes["plan"]))
        audit("plan", changes["plan"].value)

    await session.commit()
    plan = await session.scalar(select(_current_plan).select_from(User).where(User.id == user.id))
    return _to_read(user, plan)


async def audit_log(session: AsyncSession, limit: int = 100) -> list[AdminAuditEntry]:
    entries = await session.scalars(
        select(AdminAuditEntry).order_by(AdminAuditEntry.id.desc()).limit(limit)
    )
    return list(entries)
