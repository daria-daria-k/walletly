from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Category, Transaction
from app.models.enums import TransactionType
from app.services.insights import build_insights
from tests.conftest import AuthedUser, RegisterFn

pytestmark = pytest.mark.anyio

TODAY = date(2026, 11, 15)  # половина месяца: 30 дней, удобно считать


class Ledger:
    def __init__(self, session: AsyncSession, user: AuthedUser, account_id: int, category: Category):
        self.session, self.user, self.account_id, self.category = session, user, account_id, category

    def spend(self, amount: str, day: date, category_id: int | None = None, text: str | None = None):
        self.session.add(
            Transaction(
                ledger_id=self.user.ledger_id,
                user_id=self.user.id,
                type=TransactionType.EXPENSE,
                amount=Decimal(amount),
                account_id=self.account_id,
                category_id=category_id or self.category.id,
                description=text,
                tx_date=day,
            )
        )

    async def insights(self, currency: str = "RUB"):
        await self.session.commit()
        return await build_insights(self.session, self.user.ledger_id, currency, today=TODAY)


@pytest.fixture
async def ledger(session: AsyncSession, register: RegisterFn) -> Ledger:
    user = await register()
    account = Account(ledger_id=user.ledger_id, name="Сбер")
    session.add(account)
    await session.commit()
    category = await session.scalar(
        Category.__table__.select().where(
            Category.ledger_id == user.ledger_id, Category.name == "Продукты"
        )
    )
    return Ledger(session, user, account.id, await session.get(Category, category))


async def test_empty_ledger(ledger: Ledger) -> None:
    result = await ledger.insights()
    assert result.forecast.projected == 0
    assert result.forecast.baseline is None
    assert result.forecast.change_percent is None
    assert result.anomaly is None and result.overspend is None
    assert result.plan == []


async def test_forecast_extrapolates_and_compares(ledger: Ledger) -> None:
    ledger.spend("1000", date(2026, 10, 10))
    ledger.spend("1500", date(2026, 11, 10))
    forecast = (await ledger.insights()).forecast
    assert forecast.month_progress == 50
    assert forecast.projected == Decimal("3000.00")
    assert forecast.baseline == Decimal("1000.00")
    assert forecast.change_percent == 200


async def test_overspend_uses_share_of_month(ledger: Ledger) -> None:
    ledger.spend("1000", date(2026, 10, 10))
    ledger.spend("500", date(2026, 11, 10))  # ровно обычный темп за половину месяца
    assert (await ledger.insights()).overspend is None

    ledger.spend("300", date(2026, 11, 11))
    overspend = (await ledger.insights()).overspend
    assert overspend.category_name == "Продукты"
    assert overspend.amount == Decimal("300.00")


async def test_anomaly_needs_history(ledger: Ledger) -> None:
    ledger.spend("100", date(2026, 10, 1))
    ledger.spend("100", date(2026, 10, 2))
    ledger.spend("900", date(2026, 11, 5), text="Большая покупка")
    assert (await ledger.insights()).anomaly is None

    ledger.spend("100", date(2026, 10, 3))
    anomaly = (await ledger.insights()).anomaly
    assert anomaly.title == "Большая покупка"
    assert anomaly.ratio == Decimal("9.0")


async def test_limits_and_plan(ledger: Ledger) -> None:
    ledger.category.monthly_limit = Decimal("1000")
    ledger.spend("850", date(2026, 11, 2))
    result = await ledger.insights()
    assert (result.limits.total, result.limits.near, result.limits.over) == (1, 1, 0)
    assert [(p.category_name, p.has_limit) for p in result.plan] == [("Продукты", True)]

    ledger.spend("200", date(2026, 11, 3))
    limits = (await ledger.insights()).limits
    assert (limits.near, limits.over) == (0, 1)


async def test_other_currency_ignored(ledger: Ledger) -> None:
    ledger.spend("500", date(2026, 11, 2))
    assert (await ledger.insights("USD")).forecast.spent == 0


async def test_endpoint_is_scoped_to_members(
    client: AsyncClient, ledger: Ledger, register: RegisterFn
) -> None:
    url = f"/api/ledgers/{ledger.user.ledger_id}/analytics/insights"
    assert (await client.get(url, headers=ledger.user.headers)).status_code == 200
    stranger = await register("boris@example.com", "Борис")
    assert (await client.get(url, headers=stranger.headers)).status_code in (403, 404)
