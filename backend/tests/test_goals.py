from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.services.goal import forecast_goal

pytestmark = pytest.mark.anyio

D = Decimal


def test_forecast_rounds_up_and_counts_current_month() -> None:
    plan = forecast_goal(D(100_000), D(10_000), D(25_000), date(2026, 11, 15), False)
    assert plan.months_left == 4
    assert plan.forecast_month == date(2027, 2, 1)


def test_forecast_starts_next_month_after_contribution() -> None:
    plan = forecast_goal(D(100_000), D(10_000), D(25_000), date(2026, 11, 15), True)
    assert plan.months_left == 4
    assert plan.forecast_month == date(2027, 3, 1)


def test_skipped_month_moves_forecast() -> None:
    november = forecast_goal(D(1000), D(0), D(500), date(2026, 11, 1), False)
    december = forecast_goal(D(1000), D(0), D(500), date(2026, 12, 1), False)
    assert (november.forecast_month, december.forecast_month) == (date(2026, 12, 1), date(2027, 1, 1))


def test_forecast_reached() -> None:
    plan = forecast_goal(D(1000), D(1200), D(500), date(2026, 11, 1), True)
    assert plan.months_left == 0 and plan.forecast_month is None


async def _account(client, user, name="Вклад", kind="deposit", balance="0") -> dict:
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/accounts",
        json={"name": name, "kind": kind, "initial_balance": balance},
        headers=user.headers,
    )
    assert response.status_code == 201
    return response.json()


async def _goal(client, user, account_id, **extra) -> dict:
    body = {
        "name": "Отпуск",
        "target_amount": "1000",
        "monthly_contribution": "300",
        "account_id": account_id,
    }
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/goals", json=body | extra, headers=user.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_goal_needs_savings_account(client: AsyncClient, register) -> None:
    user = await register()
    card = await _account(client, user, "Карта", "card")
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/goals",
        json={"name": "Х", "target_amount": "10", "monthly_contribution": "1", "account_id": card["id"]},
        headers=user.headers,
    )
    assert response.status_code == 422


async def test_contribution_with_transfer_moves_money(client: AsyncClient, register) -> None:
    user = await register()
    card = await _account(client, user, "Карта", "card", "500")
    deposit = await _account(client, user)
    goal = await _goal(client, user, deposit["id"])
    assert goal["months_left"] == 4 and goal["reminder_due"] is True

    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/goals/{goal['id']}/contributions",
        json={"amount": "200", "from_account_id": card["id"]},
        headers=user.headers,
    )
    assert response.status_code == 201
    updated = response.json()
    assert D(updated["saved"]) == 200 and updated["progress_percent"] == 20
    assert updated["contributed_this_month"] is True and updated["reminder_due"] is False

    accounts = (await client.get(f"/api/ledgers/{user.ledger_id}/accounts", headers=user.headers)).json()
    balances = {item["name"]: D(item["balance"]) for item in accounts}
    assert balances == {"Карта": 300, "Вклад": 200}

    # Перевод в копилку не должен выглядеть как расход
    summary = (
        await client.get(f"/api/ledgers/{user.ledger_id}/analytics/summary", headers=user.headers)
    ).json()
    assert D(summary["expense"]) == 0


async def test_deleting_contribution_cancels_transfer(client: AsyncClient, register) -> None:
    user = await register()
    card = await _account(client, user, "Карта", "card", "500")
    deposit = await _account(client, user)
    goal = await _goal(client, user, deposit["id"])
    url = f"/api/ledgers/{user.ledger_id}/goals/{goal['id']}/contributions"
    await client.post(url, json={"amount": "200", "from_account_id": card["id"]}, headers=user.headers)
    item = (await client.get(url, headers=user.headers)).json()[0]

    assert (await client.delete(f"{url}/{item['id']}", headers=user.headers)).status_code == 204
    accounts = (await client.get(f"/api/ledgers/{user.ledger_id}/accounts", headers=user.headers)).json()
    assert {item["name"]: D(item["balance"]) for item in accounts} == {"Карта": 500, "Вклад": 0}


async def test_contribution_without_transfer_keeps_balances(client: AsyncClient, register) -> None:
    user = await register()
    deposit = await _account(client, user, balance="700")
    goal = await _goal(client, user, deposit["id"])
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/goals/{goal['id']}/contributions",
        json={"amount": "700"},
        headers=user.headers,
    )
    assert D(response.json()["saved"]) == 700
    accounts = (await client.get(f"/api/ledgers/{user.ledger_id}/accounts", headers=user.headers)).json()
    assert D(accounts[0]["balance"]) == 700


async def test_foreign_user_cannot_see_goal(client: AsyncClient, register) -> None:
    owner = await register("o@example.com")
    stranger = await register("s@example.com")
    deposit = await _account(client, owner)
    await _goal(client, owner, deposit["id"])
    response = await client.get(f"/api/ledgers/{owner.ledger_id}/goals", headers=stranger.headers)
    assert response.status_code == 404


async def test_goal_cannot_use_account_from_other_ledger(client: AsyncClient, register) -> None:
    owner = await register("o@example.com")
    stranger = await register("s@example.com")
    foreign = await _account(client, stranger)
    response = await client.post(
        f"/api/ledgers/{owner.ledger_id}/goals",
        json={"name": "Х", "target_amount": "10", "monthly_contribution": "1", "account_id": foreign["id"]},
        headers=owner.headers,
    )
    assert response.status_code == 404


async def test_move_goal_to_shared_ledger_keeps_saved(client: AsyncClient, register) -> None:
    user = await register()
    deposit = await _account(client, user)
    goal = await _goal(client, user, deposit["id"])
    base = f"/api/ledgers/{user.ledger_id}/goals/{goal['id']}"
    await client.post(f"{base}/contributions", json={"amount": "100"}, headers=user.headers)

    shared = (await client.post("/api/ledgers", json={"name": "Семья"}, headers=user.headers)).json()
    target = (
        await client.post(
            f"/api/ledgers/{shared['id']}/accounts",
            json={"name": "Общий", "kind": "savings"},
            headers=user.headers,
        )
    ).json()
    response = await client.post(
        f"{base}/move",
        json={"target_ledger_id": shared["id"], "account_id": target["id"]},
        headers=user.headers,
    )
    assert response.status_code == 200
    assert response.json()["ledger_id"] == shared["id"] and D(response.json()["saved"]) == 100
    assert (await client.get(f"/api/ledgers/{user.ledger_id}/goals", headers=user.headers)).json() == []


async def test_cannot_move_goal_into_foreign_ledger(client: AsyncClient, register) -> None:
    user = await register("o@example.com")
    stranger = await register("s@example.com")
    deposit = await _account(client, user)
    goal = await _goal(client, user, deposit["id"])
    foreign = await _account(client, stranger)
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/goals/{goal['id']}/move",
        json={"target_ledger_id": stranger.ledger_id, "account_id": foreign["id"]},
        headers=user.headers,
    )
    assert response.status_code == 404
