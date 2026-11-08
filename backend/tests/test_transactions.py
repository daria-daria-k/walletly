from dataclasses import dataclass
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LedgerMember
from tests.conftest import AuthedUser, RegisterFn

pytestmark = pytest.mark.anyio


@dataclass
class World:
    user: AuthedUser
    base: str
    sber: int
    cash: int
    usd: int
    food: int  # расходная категория
    salary: int  # доходная категория


@pytest.fixture
async def world(client: AsyncClient, register: RegisterFn) -> World:
    return await make_world(client, await register())


async def make_world(client: AsyncClient, user: AuthedUser) -> World:
    base = f"/api/ledgers/{user.ledger_id}"

    async def account(name: str, **fields) -> int:
        body = {"name": name} | fields
        return (await client.post(f"{base}/accounts", json=body, headers=user.headers)).json()["id"]

    groups = (await client.get(f"{base}/category-groups", headers=user.headers)).json()
    return World(
        user=user,
        base=base,
        sber=await account("Сбер", initial_balance="1000"),
        cash=await account("Наличные"),
        usd=await account("Доллары", currency="USD"),
        food=groups[1]["categories"][0]["id"],
        salary=groups[0]["categories"][0]["id"],
    )


async def post_tx(client: AsyncClient, w: World, **fields):
    body = {"amount": "100", "tx_date": "2026-10-15", "account_id": w.sber} | fields
    return await client.post(f"{w.base}/transactions", json=body, headers=w.user.headers)


async def expense(client: AsyncClient, w: World, **fields) -> dict:
    response = await post_tx(client, w, type="expense", category_id=w.food, **fields)
    assert response.status_code == 201, response.text
    return response.json()


async def balances(client: AsyncClient, w: World) -> dict[str, str]:
    response = await client.get(f"{w.base}/accounts", headers=w.user.headers)
    return {a["name"]: a["balance"] for a in response.json()}


async def test_balance_follows_all_operation_types(client: AsyncClient, world: World) -> None:
    await post_tx(client, world, type="income", category_id=world.salary, amount="500")
    await expense(client, world, amount="200.50")
    await post_tx(client, world, type="transfer", to_account_id=world.cash, amount="300")

    result = await balances(client, world)
    assert result["Сбер"] == "999.50"  # 1000 + 500 − 200.50 − 300
    assert result["Наличные"] == "300.00"


async def test_deleted_operation_leaves_balance_and_list(client: AsyncClient, world: World) -> None:
    tx = await expense(client, world, amount="100")
    url = f"{world.base}/transactions/{tx['id']}"
    assert (await client.delete(url, headers=world.user.headers)).status_code == 204

    assert (await balances(client, world))["Сбер"] == "1000.00"
    page = await client.get(f"{world.base}/transactions", headers=world.user.headers)
    assert page.json()["total"] == 0
    assert (await client.get(url, headers=world.user.headers)).status_code == 404


async def test_account_with_operations_cannot_be_deleted(client: AsyncClient, world: World) -> None:
    await expense(client, world)
    response = await client.delete(
        f"{world.base}/accounts/{world.sber}", headers=world.user.headers
    )
    assert response.status_code == 409


async def test_category_with_operations_cannot_be_deleted(
    client: AsyncClient, world: World
) -> None:
    await expense(client, world)
    response = await client.delete(
        f"{world.base}/categories/{world.food}", headers=world.user.headers
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "fields",
    [
        {"type": "expense"},  # нет категории
        {"type": "transfer"},  # нет счёта зачисления
        {"type": "expense", "category_id": "SALARY"},  # доходная категория у расхода
        {"type": "transfer", "to_account_id": "SBER"},  # перевод на тот же счёт
        {"type": "transfer", "to_account_id": "USD"},  # разные валюты
        {"type": "expense", "category_id": "FOOD", "to_account_id": "CASH"},
        {"type": "transfer", "to_account_id": "CASH", "category_id": "FOOD"},
        {"type": "expense", "category_id": "FOOD", "amount": "0"},
        {"type": "expense", "category_id": "FOOD", "amount": "-5"},
        {"type": "expense", "category_id": "FOOD", "amount": "1.999"},
    ],
)
async def test_invalid_operation_rejected(client: AsyncClient, world: World, fields: dict) -> None:
    ids = {"SALARY": world.salary, "SBER": world.sber, "USD": world.usd, "CASH": world.cash, "FOOD": world.food}
    resolved = {k: ids.get(v, v) if isinstance(v, str) else v for k, v in fields.items()}
    assert (await post_tx(client, world, **resolved)).status_code == 422


async def test_cannot_use_account_from_other_ledger(
    client: AsyncClient, world: World, register: RegisterFn
) -> None:
    boris = await make_world(client, await register("boris@example.com", "Борис"))
    response = await post_tx(
        client, boris, type="expense", category_id=boris.food, account_id=world.sber
    )
    assert response.status_code == 422


async def test_archived_account_rejected_for_new_operation(
    client: AsyncClient, world: World
) -> None:
    await client.patch(
        f"{world.base}/accounts/{world.cash}", json={"is_active": False}, headers=world.user.headers
    )
    response = await post_tx(client, world, type="expense", category_id=world.food, account_id=world.cash)
    assert response.status_code == 422


async def test_old_operation_on_archived_account_still_editable(
    client: AsyncClient, world: World
) -> None:
    tx = await expense(client, world)
    headers = world.user.headers
    await client.patch(f"{world.base}/accounts/{world.sber}", json={"is_active": False}, headers=headers)
    response = await client.patch(
        f"{world.base}/transactions/{tx['id']}", json={"description": "уточнил"}, headers=headers
    )
    assert response.status_code == 200


async def test_update_revalidates_merged_state(client: AsyncClient, world: World) -> None:
    tx = await expense(client, world)
    url = f"{world.base}/transactions/{tx['id']}"
    # Сменили только тип: категория расходная и теперь не подходит
    response = await client.patch(url, json={"type": "income"}, headers=world.user.headers)
    assert response.status_code == 422

    response = await client.patch(
        url, json={"type": "income", "category_id": world.salary}, headers=world.user.headers
    )
    assert response.status_code == 200


async def test_expense_can_become_transfer(client: AsyncClient, world: World) -> None:
    tx = await expense(client, world)
    response = await client.patch(
        f"{world.base}/transactions/{tx['id']}",
        json={"type": "transfer", "category_id": None, "to_account_id": world.cash},
        headers=world.user.headers,
    )
    assert response.status_code == 200
    assert (await balances(client, world))["Наличные"] == "100.00"


async def test_filters_and_pagination(client: AsyncClient, world: World) -> None:
    await expense(client, world, description="Кофе 100%", tx_date="2026-10-01")
    await expense(client, world, description="Кофе", tx_date="2026-10-02")
    await expense(client, world, description="Такси", tx_date="2026-11-01", account_id=world.cash)
    url = f"{world.base}/transactions"

    async def ids(**params) -> list[str]:
        response = await client.get(url, params=params, headers=world.user.headers)
        return [item["description"] for item in response.json()["items"]]

    assert await ids() == ["Такси", "Кофе", "Кофе 100%"]  # новые сверху
    assert await ids(search="кофе") == ["Кофе", "Кофе 100%"]
    assert await ids(search="%") == ["Кофе 100%"]  # % — буквальный символ
    assert await ids(date_from="2026-10-02", date_to="2026-10-31") == ["Кофе"]
    assert await ids(account_id=world.cash) == ["Такси"]
    assert await ids(limit=1, offset=1) == ["Кофе"]


async def test_member_edits_only_own_operations(
    client: AsyncClient, session: AsyncSession, world: World, register: RegisterFn
) -> None:
    boris = await register("boris@example.com", "Борис")
    session.add(LedgerMember(ledger_id=world.user.ledger_id, user_id=boris.id))
    await session.commit()
    tx = await expense(client, world)
    url = f"{world.base}/transactions/{tx['id']}"

    assert (await client.delete(url, headers=boris.headers)).status_code == 403

    body = {"type": "expense", "amount": "5", "tx_date": "2026-10-15", "account_id": world.sber, "category_id": world.food}
    own = await client.post(f"{world.base}/transactions", json=body, headers=boris.headers)
    assert own.json()["author_name"] == "Борис"
    own_url = f"{world.base}/transactions/{own.json()['id']}"
    assert (await client.delete(own_url, headers=boris.headers)).status_code == 204
    # Владелец пространства может поправить любую операцию
    other = await client.post(f"{world.base}/transactions", json=body, headers=boris.headers)
    other_url = f"{world.base}/transactions/{other.json()['id']}"
    assert (await client.delete(other_url, headers=world.user.headers)).status_code == 204


async def test_analytics_excludes_transfers_and_other_currency(
    client: AsyncClient, world: World
) -> None:
    await post_tx(client, world, type="income", category_id=world.salary, amount="1000", tx_date="2026-09-10")
    await expense(client, world, amount="300", tx_date="2026-09-20")
    await expense(client, world, amount="50", tx_date="2026-10-05")
    await post_tx(client, world, type="transfer", to_account_id=world.cash, amount="400")
    await expense(client, world, amount="7", account_id=world.usd)
    headers = world.user.headers
    base = f"{world.base}/analytics"

    summary = (await client.get(f"{base}/summary", headers=headers)).json()
    assert summary == {"income": "1000.00", "expense": "350.00", "net": "650.00"}

    usd = (await client.get(f"{base}/summary", params={"currency": "USD"}, headers=headers)).json()
    assert usd["expense"] == "7.00"

    september = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
    rows = (await client.get(f"{base}/by-category", params=september, headers=headers)).json()
    assert [(r["category_name"], r["group_name"], r["total"]) for r in rows] == [
        ("Продукты", "Базовые", "300.00")
    ]

    months = (await client.get(f"{base}/monthly", headers=headers)).json()
    assert months == [
        {"month": "2026-09", "income": "1000.00", "expense": "300.00"},
        {"month": "2026-10", "income": "0", "expense": "50.00"},
    ]


async def test_account_month_change_counts_only_this_month(
    client: AsyncClient, world: World
) -> None:
    today = date.today()
    previous_month = today.replace(day=1) - timedelta(days=1)
    await expense(client, world, amount="70", tx_date=previous_month.isoformat())
    await expense(client, world, amount="30", tx_date=today.isoformat())

    accounts = (await client.get(f"{world.base}/accounts", headers=world.user.headers)).json()
    sber = next(a for a in accounts if a["name"] == "Сбер")
    assert (sber["balance"], sber["month_change"]) == ("900.00", "-30.00")


async def test_expenses_by_author(
    client: AsyncClient, session: AsyncSession, world: World, register: RegisterFn
) -> None:
    boris = await register("boris@example.com", "Борис")
    session.add(LedgerMember(ledger_id=world.user.ledger_id, user_id=boris.id))
    await session.commit()
    await expense(client, world, amount="100")
    body = {"type": "expense", "amount": "300", "tx_date": "2026-10-15", "account_id": world.sber, "category_id": world.food}
    await client.post(f"{world.base}/transactions", json=body, headers=boris.headers)

    rows = (await client.get(f"{world.base}/analytics/by-author", headers=world.user.headers)).json()
    assert [(r["name"], r["total"]) for r in rows] == [("Борис", "300.00"), ("Анна", "100.00")]
