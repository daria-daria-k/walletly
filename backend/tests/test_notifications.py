from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.notification import run_checks

pytestmark = pytest.mark.anyio

TODAY = date.today()


async def _setup_limit(client, user, limit="1000"):
    h = user.headers
    base = f"/api/ledgers/{user.ledger_id}"
    account = (await client.post(f"{base}/accounts", json={"name": "Карта"}, headers=h)).json()
    groups = (await client.get(f"{base}/category-groups", headers=h)).json()
    category = next(g for g in groups if g["type"] == "expense")["categories"][0]
    await client.patch(f"{base}/categories/{category['id']}", json={"monthly_limit": limit}, headers=h)
    return account, category


async def _spend(client, user, account, category, amount):
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/transactions",
        json={
            "type": "expense",
            "amount": amount,
            "account_id": account["id"],
            "category_id": category["id"],
            "tx_date": TODAY.isoformat(),
        },
        headers=user.headers,
    )
    assert response.status_code == 201, response.text


async def _list(client, user) -> dict:
    return (await client.get("/api/notifications", headers=user.headers)).json()


async def test_budget_warning_then_over_without_duplicates(
    client: AsyncClient, register, session: AsyncSession
) -> None:
    user = await register()
    account, category = await _setup_limit(client, user)
    await _spend(client, user, account, category, "850")

    assert [item.kind for item in await run_checks(session, TODAY)] == ["budget"]
    # Повторная проверка в тот же час не должна присылать то же самое
    assert await run_checks(session, TODAY) == []

    await _spend(client, user, account, category, "200")
    created = await run_checks(session, TODAY)
    assert len(created) == 1 and "превышен" in created[0].title
    assert (await _list(client, user))["unread"] == 2


async def test_disabled_setting_is_respected(
    client: AsyncClient, register, session: AsyncSession
) -> None:
    user = await register()
    await client.patch(
        "/api/auth/me",
        json={"notifications": {"budget": False, "unusual": True, "weekly": True, "family": True}},
        headers=user.headers,
    )
    account, category = await _setup_limit(client, user)
    await _spend(client, user, account, category, "1500")
    assert await run_checks(session, TODAY) == []


async def test_goal_reminder(client: AsyncClient, register, session: AsyncSession) -> None:
    user = await register()
    base = f"/api/ledgers/{user.ledger_id}"
    deposit = (
        await client.post(f"{base}/accounts", json={"name": "Вклад", "kind": "deposit"}, headers=user.headers)
    ).json()
    await client.post(
        f"{base}/goals",
        json={"name": "Отпуск", "target_amount": "100", "monthly_contribution": "10", "account_id": deposit["id"]},
        headers=user.headers,
    )
    created = await run_checks(session, TODAY)
    assert [item.kind for item in created] == ["goal"]


async def test_family_notifies_only_others(
    client: AsyncClient, register, session: AsyncSession
) -> None:
    owner = await register("o@example.com")
    partner = await register("p@example.com")
    shared = (await client.post("/api/ledgers", json={"name": "Семья"}, headers=owner.headers)).json()
    invite = (
        await client.post(
            f"/api/ledgers/{shared['id']}/invitations", json={"email": "p@example.com"}, headers=owner.headers
        )
    ).json()
    invited = await run_checks(session, TODAY)
    assert [item.user.email for item in invited] == ["p@example.com"]
    await client.post(f"/api/invitations/{invite['token']}/accept", headers=partner.headers)

    base = f"/api/ledgers/{shared['id']}"
    account = (await client.post(f"{base}/accounts", json={"name": "Общий"}, headers=owner.headers)).json()
    groups = (await client.get(f"{base}/category-groups", headers=owner.headers)).json()
    category = next(g for g in groups if g["type"] == "expense")["categories"][0]
    await client.post(
        f"{base}/transactions",
        json={"type": "expense", "amount": "10", "account_id": account["id"], "category_id": category["id"], "tx_date": TODAY.isoformat()},
        headers=owner.headers,
    )
    created = await run_checks(session, TODAY)
    assert [item.user.email for item in created if item.kind == "family"] == ["p@example.com"]


async def test_read_marks(client: AsyncClient, register, session: AsyncSession) -> None:
    user = await register("a@example.com")
    stranger = await register("b@example.com")
    account, category = await _setup_limit(client, user)
    await _spend(client, user, account, category, "1500")
    await run_checks(session, TODAY)
    item = (await _list(client, user))["items"][0]

    # Чужой номер не срабатывает, но и не выдаёт, что такое уведомление есть
    response = await client.post(f"/api/notifications/{item['id']}/read", headers=stranger.headers)
    assert response.status_code == 204
    assert (await _list(client, user))["unread"] == 1

    await client.post(f"/api/notifications/{item['id']}/read", headers=user.headers)
    assert (await _list(client, user))["unread"] == 0
