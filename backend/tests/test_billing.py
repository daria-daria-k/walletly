from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, Subscription
from app.services import yookassa
from app.services.yookassa import ProviderPayment

pytestmark = pytest.mark.anyio


class FakeYookassa:
    """Вместо настоящей ЮKassa: запоминает статус, который «вернёт» её API."""

    def __init__(self) -> None:
        self.status = "pending"
        self.amount = Decimal(299)

    def _payment(self, url: str | None = None) -> ProviderPayment:
        return ProviderPayment("yk-1", self.status, self.status == "succeeded", self.amount, url)

    async def create_payment(self, *args, **kwargs) -> ProviderPayment:
        return self._payment("https://yookassa.example/pay")

    async def get_payment(self, provider_id: str) -> ProviderPayment:
        return self._payment()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeYookassa:
    fake = FakeYookassa()
    monkeypatch.setattr(yookassa, "create_payment", fake.create_payment)
    monkeypatch.setattr(yookassa, "get_payment", fake.get_payment)
    monkeypatch.setattr(yookassa, "is_configured", lambda: True)
    return fake


WEBHOOK = {"event": "payment.succeeded", "object": {"id": "yk-1", "status": "succeeded"}}


async def _plan(client, user) -> str:
    return (await client.get("/api/auth/me", headers=user.headers)).json()["plan"]


async def _checkout(client, user) -> None:
    response = await client.post("/api/billing/checkout", headers=user.headers)
    assert response.status_code == 200
    assert response.json()["confirmation_url"] == "https://yookassa.example/pay"


async def test_webhook_activates_premium_after_real_payment(client: AsyncClient, register, provider) -> None:
    user = await register()
    await _checkout(client, user)
    assert await _plan(client, user) == "free"

    provider.status = "succeeded"
    assert (await client.post("/api/billing/yookassa/webhook", json=WEBHOOK)).status_code == 200
    assert await _plan(client, user) == "premium"


async def test_forged_webhook_does_nothing(client: AsyncClient, register, provider) -> None:
    user = await register()
    await _checkout(client, user)
    # Запрос утверждает, что оплата прошла, но API ЮKassa говорит, что нет
    await client.post("/api/billing/yookassa/webhook", json=WEBHOOK)
    assert await _plan(client, user) == "free"


async def test_repeated_webhook_extends_once(
    client: AsyncClient, register, provider, session: AsyncSession
) -> None:
    user = await register()
    await _checkout(client, user)
    provider.status = "succeeded"
    await client.post("/api/billing/yookassa/webhook", json=WEBHOOK)
    await client.post("/api/billing/yookassa/webhook", json=WEBHOOK)
    rows = (
        await session.scalars(select(Subscription).where(Subscription.user_id == user.id, Subscription.plan == "premium"))
    ).all()
    assert len(rows) == 1


async def test_wrong_amount_is_not_accepted(client: AsyncClient, register, provider) -> None:
    user = await register()
    await _checkout(client, user)
    provider.status = "succeeded"
    provider.amount = Decimal(1)
    await client.post("/api/billing/yookassa/webhook", json=WEBHOOK)
    assert await _plan(client, user) == "free"


async def test_payment_before_expiry_adds_days(
    client: AsyncClient, register, provider, session: AsyncSession
) -> None:
    user = await register()
    ends = datetime.now(UTC) + timedelta(days=10)
    session.add(Subscription(user_id=user.id, plan="premium", expires_at=ends))
    await session.commit()

    await _checkout(client, user)
    provider.status = "succeeded"
    await client.post("/api/billing/yookassa/webhook", json=WEBHOOK)
    me = (await client.get("/api/auth/me", headers=user.headers)).json()
    new_end = datetime.fromisoformat(me["plan_expires_at"])
    assert abs(new_end - (ends + timedelta(days=30))) < timedelta(seconds=5)


async def test_expired_premium_falls_back_to_free(
    client: AsyncClient, register, session: AsyncSession
) -> None:
    user = await register()
    session.add(
        Subscription(user_id=user.id, plan="premium", expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await session.commit()
    assert await _plan(client, user) == "free"


async def test_sync_only_for_owner(client: AsyncClient, register, provider, session: AsyncSession) -> None:
    owner = await register("o@example.com")
    stranger = await register("s@example.com")
    await _checkout(client, owner)
    payment = await session.scalar(select(Payment))
    url = f"/api/billing/payments/{payment.id}/sync"
    assert (await client.post(url, headers=stranger.headers)).status_code == 404
    provider.status = "succeeded"
    response = await client.post(url, headers=owner.headers)
    assert response.json()["status"] == "succeeded"
    assert await _plan(client, owner) == "premium"


async def test_checkout_without_keys(client: AsyncClient, register) -> None:
    user = await register()
    response = await client.post("/api/billing/checkout", headers=user.headers)
    assert response.status_code == 409


async def test_free_plan_is_limited_to_one_goal(client: AsyncClient, register, session: AsyncSession) -> None:
    user = await register()
    base = f"/api/ledgers/{user.ledger_id}"
    deposit = (
        await client.post(f"{base}/accounts", json={"name": "Вклад", "kind": "deposit"}, headers=user.headers)
    ).json()
    body = {"name": "А", "target_amount": "100", "monthly_contribution": "10", "account_id": deposit["id"]}
    assert (await client.post(f"{base}/goals", json=body, headers=user.headers)).status_code == 201
    assert (await client.post(f"{base}/goals", json=body, headers=user.headers)).status_code == 403

    session.add(Subscription(user_id=user.id, plan="premium"))
    await session.commit()
    assert (await client.post(f"{base}/goals", json=body, headers=user.headers)).status_code == 201
