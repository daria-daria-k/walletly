"""Уведомления: проверки по расписанию, создание записей и чтение колокольчика."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Account,
    Category,
    Invitation,
    Ledger,
    LedgerMember,
    Notification,
    Transaction,
    User,
)
from app.models.enums import InvitationStatus, LedgerType, TransactionType
from app.schemas.auth import NotificationSettings
from app.services.analytics import scoped_transactions
from app.services.goal import list_goals
from app.services.insights import build_insights

_LIMIT_WARNING = Decimal("0.8")
_KEEP_READ_DAYS = 90
_LAST_ITEMS = 30


@dataclass(frozen=True)
class NewNotification:
    user: User
    kind: str
    title: str
    body: str
    link: str


def _money(amount: Decimal, currency: str) -> str:
    return f"{amount:,.0f}".replace(",", " ") + f" {currency}"


class _Collector:
    """Складывает уведомления и не даёт отправить одно и то же дважды."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.created: list[NewNotification] = []

    async def add(
        self, user: User, kind: str, dedupe_key: str, title: str, body: str, link: str
    ) -> None:
        # Проверки идут каждый час. Уникальный ключ в БД решает, было ли уже такое событие,
        # и работает, даже если две проверки случайно запустятся одновременно
        inserted = await self.session.scalar(
            insert(Notification)
            .values(
                user_id=user.id, kind=kind, dedupe_key=dedupe_key, title=title, body=body, link=link
            )
            .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
            .returning(Notification.id)
        )
        if inserted is not None:
            self.created.append(NewNotification(user, kind, title, body, link))


async def _check_budget(
    collect: _Collector, ledger: Ledger, users: list[User], currency: str, today: date
) -> None:
    month_start = today.replace(day=1)
    rows = await collect.session.execute(
        scoped_transactions(
            select(Category.id, Category.name, Category.monthly_limit, func.sum(Transaction.amount))
            .join(Category, Category.id == Transaction.category_id)
            .where(Transaction.type == TransactionType.EXPENSE, Category.monthly_limit.is_not(None))
            .group_by(Category.id),
            ledger.id,
            currency,
            month_start,
            today,
        )
    )
    for category_id, name, limit, spent in rows:
        if limit <= 0 or spent < limit * _LIMIT_WARNING:
            continue
        over = spent >= limit
        level = 100 if over else 80
        title = f"Лимит «{name}» превышен" if over else f"Лимит «{name}» почти исчерпан"
        body = f"Потрачено {_money(spent, currency)} из {_money(limit, currency)}"
        for user in users:
            if _prefs(user).budget:
                await collect.add(
                    user,
                    "budget",
                    f"budget:{category_id}:{month_start:%Y-%m}:{level}",
                    title,
                    body,
                    "/categories",
                )


def _prefs(user: User) -> NotificationSettings:
    return NotificationSettings.model_validate(user.notifications)


async def _check_anomaly(
    collect: _Collector, ledger: Ledger, users: list[User], currency: str, today: date
) -> None:
    anomaly = (await build_insights(collect.session, ledger.id, currency)).anomaly
    if anomaly is None:
        return
    for user in users:
        if _prefs(user).unusual:
            await collect.add(
                user,
                "unusual",
                f"anomaly:{anomaly.transaction_id}",
                "Необычная трата",
                f"{anomaly.title}: {_money(anomaly.amount, currency)}, в {anomaly.ratio} раза больше обычного",
                "/ai",
            )


async def _check_goals(collect: _Collector, ledger: Ledger, users: list[User], today: date) -> None:
    for goal in await list_goals(collect.session, ledger.id):
        if not goal.reminder_due:
            continue
        for user in users:
            await collect.add(
                user,
                "goal",
                f"goal:{goal.id}:{today:%Y-%m}",
                f"Пора пополнить копилку «{goal.name}»",
                f"Плановый взнос: {_money(goal.monthly_contribution, goal.currency)}",
                "/goals",
            )


async def _check_family(collect: _Collector, ledger: Ledger, users: list[User], today: date) -> None:
    start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    rows = await collect.session.execute(
        select(Transaction.user_id, func.count())
        .where(
            Transaction.ledger_id == ledger.id,
            Transaction.is_deleted.is_(False),
            Transaction.created_at >= start,
        )
        .group_by(Transaction.user_id)
    )
    by_author = dict(rows.all())
    for user in users:
        # Свои операции человек и так видел
        foreign = sum(count for author, count in by_author.items() if author != user.id)
        if foreign and _prefs(user).family:
            await collect.add(
                user,
                "family",
                f"family:{ledger.id}:{today:%Y-%m-%d}",
                f"Новые операции в «{ledger.name}»",
                "Участники добавили операции сегодня",
                "/transactions",
            )


async def _check_weekly(collect: _Collector, ledger: Ledger, users: list[User], today: date) -> None:
    week = today.isocalendar()
    total = await collect.session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.ledger_id == ledger.id,
            Transaction.is_deleted.is_(False),
            Transaction.type == TransactionType.EXPENSE,
            Transaction.tx_date > today - timedelta(days=7),
            Transaction.tx_date <= today,
        )
    )
    if not total:
        return
    for user in users:
        if _prefs(user).weekly:
            await collect.add(
                user,
                "weekly",
                f"weekly:{ledger.id}:{week.year}-{week.week}",
                f"Итоги недели: {ledger.name}",
                f"Расходы за 7 дней: {total:,.0f}".replace(",", " "),
                "/analytics",
            )


async def _check_invitations(collect: _Collector, today: date) -> None:
    rows = await collect.session.execute(
        select(Invitation, User, Ledger.name)
        .join(User, User.email == Invitation.email)
        .join(Ledger, Ledger.id == Invitation.ledger_id)
        .where(
            Invitation.status == InvitationStatus.PENDING,
            Invitation.expires_at > datetime.now(UTC),
            User.is_active.is_(True),
        )
    )
    for invitation, user, ledger_name in rows:
        if _prefs(user).family:
            await collect.add(
                user,
                "family",
                f"invite:{invitation.id}",
                f"Приглашение в «{ledger_name}»",
                "Вас пригласили вести бюджет вместе",
                f"/invite/{invitation.token}",
            )


async def run_checks(session: AsyncSession, today: date | None = None) -> list[NewNotification]:
    """Одна транзакция на весь проход: новые записи видны только все вместе."""
    today = today or date.today()
    collect = _Collector(session)
    ledgers = await session.scalars(
        select(Ledger).options(selectinload(Ledger.members).joinedload(LedgerMember.user))
    )
    for ledger in ledgers.unique():
        users = [member.user for member in ledger.members if member.user.is_active]
        if not users:
            continue
        currencies = (
            await session.scalars(
                select(Account.currency)
                .where(Account.ledger_id == ledger.id, Account.is_active.is_(True))
                .distinct()
            )
        ).all()
        for currency in currencies:
            await _check_budget(collect, ledger, users, currency, today)
            await _check_anomaly(collect, ledger, users, currency, today)
        await _check_goals(collect, ledger, users, today)
        if ledger.type == LedgerType.SHARED:
            await _check_family(collect, ledger, users, today)
        if today.weekday() == 6:  # воскресенье
            await _check_weekly(collect, ledger, users, today)
    await _check_invitations(collect, today)
    await session.commit()
    return collect.created


async def list_for_user(session: AsyncSession, user_id: int) -> tuple[list[Notification], int]:
    items = await session.scalars(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.id.desc())
        .limit(_LAST_ITEMS)
    )
    unread = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return list(items), unread


async def mark_read(session: AsyncSession, user_id: int, notification_id: int | None = None) -> None:
    """Условие по user_id не даёт отметить чужое уведомление, подставив его номер."""
    query = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    if notification_id is not None:
        query = query.where(Notification.id == notification_id)
    await session.execute(query)
    await session.commit()


async def delete_old(session: AsyncSession) -> None:
    await session.execute(
        delete(Notification).where(
            Notification.created_at < datetime.now(UTC) - timedelta(days=_KEEP_READ_DAYS)
        )
    )
    await session.commit()
