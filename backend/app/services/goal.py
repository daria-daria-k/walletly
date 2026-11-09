from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import Account, GoalContribution, Ledger, SavingsGoal, Transaction, User
from app.models.enums import AccountKind, Plan, TransactionType
from app.schemas.goal import (
    ContributionCreate,
    ContributionRead,
    GoalCreate,
    GoalMove,
    GoalRead,
    GoalUpdate,
)
from app.services.billing import get_plan
from app.services.errors import (
    ConflictError,
    InvalidDataError,
    NotFoundError,
    PermissionDeniedError,
)
from app.services.scoped import get_in_ledger

FREE_GOALS = 1
_SAVINGS_KINDS = (AccountKind.SAVINGS, AccountKind.DEPOSIT, AccountKind.CASH)


def _add_months(month_start: date, months: int) -> date:
    index = month_start.year * 12 + month_start.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


@dataclass(frozen=True)
class Forecast:
    months_left: int
    forecast_month: date | None


def forecast_goal(
    target: Decimal, saved: Decimal, monthly: Decimal, today: date, contributed_this_month: bool
) -> Forecast:
    """Сколько взносов осталось и в каком месяце будет последний.

    Считается заново при каждом запросе и хранит только остаток до цели: поэтому пропуск
    сдвигает дату сам, а взнос больше или меньше планового учитывается автоматически.
    """
    remaining = target - saved
    if remaining <= 0:
        return Forecast(0, None)
    months = int((remaining / monthly).to_integral_value(rounding=ROUND_CEILING))
    # Если в этом месяце уже пополняли, следующий взнос будет в следующем месяце
    first_payment = 1 if contributed_this_month else 0
    return Forecast(months, _add_months(today.replace(day=1), first_payment + months - 1))


def build_read(goal: SavingsGoal, today: date) -> GoalRead:
    saved = sum((item.amount for item in goal.contributions), Decimal(0))
    this_month = today.replace(day=1)
    last_month = _add_months(this_month, -1)
    contributed_this_month = any(item.contributed_on >= this_month for item in goal.contributions)
    contributed_last_month = any(
        last_month <= item.contributed_on < this_month for item in goal.contributions
    )
    plan = forecast_goal(
        goal.target_amount, saved, goal.monthly_contribution, today, contributed_this_month
    )
    reached = plan.months_left == 0
    return GoalRead(
        id=goal.id,
        ledger_id=goal.ledger_id,
        name=goal.name,
        target_amount=goal.target_amount,
        monthly_contribution=goal.monthly_contribution,
        account_id=goal.account_id,
        account_name=goal.account.name,
        currency=goal.account.currency,
        reminder_day=goal.reminder_day,
        saved=saved,
        remaining=max(goal.target_amount - saved, Decimal(0)),
        progress_percent=min(int(saved / goal.target_amount * 100), 100),
        months_left=plan.months_left,
        forecast_month=plan.forecast_month,
        contributed_this_month=contributed_this_month,
        # Копилка, созданная в этом месяце, за прошлый месяц ничего не пропускала
        missed_last_month=not reached
        and not contributed_last_month
        and goal.created_at.date() < this_month,
        reminder_due=not reached
        and not contributed_this_month
        and today.day >= goal.reminder_day,
    )


async def _check_goal_account(session: AsyncSession, ledger_id: int, account_id: int) -> Account:
    account = await get_in_ledger(session, Account, ledger_id, account_id)
    if account.kind not in _SAVINGS_KINDS or not account.is_active:
        raise InvalidDataError("Копилка хранится на накопительном счёте, вкладе или в наличных")
    return account


async def _get_goal(session: AsyncSession, ledger_id: int, goal_id: int) -> SavingsGoal:
    goal = await session.scalar(
        select(SavingsGoal)
        .options(joinedload(SavingsGoal.account), selectinload(SavingsGoal.contributions))
        .where(SavingsGoal.id == goal_id, SavingsGoal.ledger_id == ledger_id)
        # Иначе после commit вернулись бы данные, прочитанные до изменения
        .execution_options(populate_existing=True)
    )
    if goal is None:
        raise NotFoundError("Копилка не найдена")
    return goal


async def list_goals(session: AsyncSession, ledger_id: int) -> list[GoalRead]:
    goals = await session.scalars(
        select(SavingsGoal)
        .options(joinedload(SavingsGoal.account), selectinload(SavingsGoal.contributions))
        .where(SavingsGoal.ledger_id == ledger_id)
        .order_by(SavingsGoal.id)
    )
    today = date.today()
    return [build_read(goal, today) for goal in goals]


async def create_goal(
    session: AsyncSession, ledger_id: int, user_id: int, data: GoalCreate
) -> GoalRead:
    existing = await session.scalar(
        select(func.count()).select_from(SavingsGoal).where(SavingsGoal.ledger_id == ledger_id)
    )
    if existing >= FREE_GOALS and await get_plan(session, user_id) != Plan.PREMIUM:
        raise PermissionDeniedError("Больше одной копилки доступно в тарифе Premium")
    await _check_goal_account(session, ledger_id, data.account_id)
    goal = SavingsGoal(ledger_id=ledger_id, **data.model_dump())
    session.add(goal)
    await session.commit()
    return build_read(await _get_goal(session, ledger_id, goal.id), date.today())


async def update_goal(
    session: AsyncSession, ledger_id: int, goal_id: int, data: GoalUpdate
) -> GoalRead:
    goal = await _get_goal(session, ledger_id, goal_id)
    changes = data.model_dump(exclude_unset=True)
    if "account_id" in changes:
        await _check_goal_account(session, ledger_id, changes["account_id"])
    for field, value in changes.items():
        setattr(goal, field, value)
    await session.commit()
    return build_read(await _get_goal(session, ledger_id, goal.id), date.today())


async def delete_goal(session: AsyncSession, ledger_id: int, goal_id: int) -> None:
    goal = await _get_goal(session, ledger_id, goal_id)
    await session.delete(goal)
    await session.commit()


async def move_goal(session: AsyncSession, ledger_id: int, goal_id: int, data: GoalMove) -> GoalRead:
    """Делает копилку личной или общей. Право на целевое пространство проверяет роутер.

    Переводы, созданные раньше, остаются в старом пространстве: это уже случившаяся история,
    а накопленная сумма считается по пополнениям и не меняется.
    """
    goal = await _get_goal(session, ledger_id, goal_id)
    if await session.get(Ledger, data.target_ledger_id) is None:
        raise InvalidDataError("Пространство не найдено")
    await _check_goal_account(session, data.target_ledger_id, data.account_id)
    goal.ledger_id = data.target_ledger_id
    goal.account_id = data.account_id
    await session.commit()
    return build_read(await _get_goal(session, data.target_ledger_id, goal.id), date.today())


async def add_contribution(
    session: AsyncSession, ledger_id: int, goal_id: int, user_id: int, data: ContributionCreate
) -> GoalRead:
    goal = await _get_goal(session, ledger_id, goal_id)
    contributed_on = data.contributed_on or date.today()
    if contributed_on > date.today():
        raise InvalidDataError("Дата пополнения не может быть в будущем")

    transaction = None
    if data.from_account_id is not None:
        source = await get_in_ledger(session, Account, ledger_id, data.from_account_id)
        if source.id == goal.account_id:
            raise InvalidDataError("Выберите другой счёт: деньги уже лежат на счёте копилки")
        if source.currency != goal.account.currency:
            raise InvalidDataError("Валюта счёта должна совпадать с валютой копилки")
        # Настоящий перевод: остатки счетов сходятся, а расходом это не считается
        transaction = Transaction(
            ledger_id=ledger_id,
            user_id=user_id,
            type=TransactionType.TRANSFER,
            amount=data.amount,
            account_id=source.id,
            to_account_id=goal.account_id,
            description=f"Копилка: {goal.name}",
            tx_date=contributed_on,
        )
        session.add(transaction)
        await session.flush()

    session.add(
        GoalContribution(
            goal_id=goal.id,
            user_id=user_id,
            amount=data.amount,
            contributed_on=contributed_on,
            transaction_id=transaction.id if transaction else None,
        )
    )
    await session.commit()
    return build_read(await _get_goal(session, ledger_id, goal.id), date.today())


async def list_contributions(
    session: AsyncSession, ledger_id: int, goal_id: int
) -> list[ContributionRead]:
    await _get_goal(session, ledger_id, goal_id)
    rows = await session.execute(
        select(GoalContribution, User.name)
        .join(User, User.id == GoalContribution.user_id)
        .where(GoalContribution.goal_id == goal_id)
        .order_by(GoalContribution.contributed_on.desc(), GoalContribution.id.desc())
    )
    return [
        ContributionRead(
            id=item.id,
            user_name=name,
            amount=item.amount,
            contributed_on=item.contributed_on,
            from_transfer=item.transaction_id is not None,
            created_at=item.created_at,
        )
        for item, name in rows
    ]


async def delete_contribution(
    session: AsyncSession, ledger_id: int, goal_id: int, contribution_id: int
) -> None:
    """Перевод тоже отменяется, иначе деньги остались бы на счёте копилки без учёта в ней."""
    await _get_goal(session, ledger_id, goal_id)
    item = await session.scalar(
        select(GoalContribution).where(
            GoalContribution.id == contribution_id, GoalContribution.goal_id == goal_id
        )
    )
    if item is None:
        raise NotFoundError("Пополнение не найдено")
    if item.transaction_id is not None:
        transaction = await session.get(Transaction, item.transaction_id)
        if transaction is not None:
            transaction.is_deleted = True
    await session.delete(item)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError("Не удалось удалить пополнение") from None
