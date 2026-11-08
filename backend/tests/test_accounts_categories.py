from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LedgerMember
from tests.conftest import AuthedUser, RegisterFn

pytestmark = pytest.mark.anyio


async def create_account(client: AsyncClient, user: AuthedUser, **fields) -> dict:
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/accounts",
        json={"name": "Сбер"} | fields,
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def groups(client: AsyncClient, user: AuthedUser) -> list[dict]:
    response = await client.get(
        f"/api/ledgers/{user.ledger_id}/category-groups", headers=user.headers
    )
    return response.json()


async def test_new_account_balance_equals_initial(
    client: AsyncClient, register: RegisterFn
) -> None:
    anna = await register()
    account = await create_account(client, anna, initial_balance="1000.50")
    assert account["balance"] == "1000.50"
    assert account["currency"] == "RUB"


@pytest.mark.parametrize(
    "bad", [{"name": "  "}, {"currency": "rub"}, {"initial_balance": "1.234"}, {"name": None}]
)
async def test_invalid_account_rejected(
    client: AsyncClient, register: RegisterFn, bad: dict
) -> None:
    anna = await register()
    response = await client.post(
        f"/api/ledgers/{anna.ledger_id}/accounts",
        json={"name": "Сбер"} | bad,
        headers=anna.headers,
    )
    assert response.status_code == 422


async def test_archived_account_hidden_by_default(
    client: AsyncClient, register: RegisterFn
) -> None:
    anna = await register()
    account = await create_account(client, anna)
    url = f"/api/ledgers/{anna.ledger_id}/accounts"
    await client.patch(f"{url}/{account['id']}", json={"is_active": False}, headers=anna.headers)

    assert (await client.get(url, headers=anna.headers)).json() == []
    archived = await client.get(url, params={"include_archived": True}, headers=anna.headers)
    assert len(archived.json()) == 1


async def test_null_in_update_is_rejected(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    account = await create_account(client, anna)
    response = await client.patch(
        f"/api/ledgers/{anna.ledger_id}/accounts/{account['id']}",
        json={"name": None},
        headers=anna.headers,
    )
    assert response.status_code == 422


async def test_cannot_touch_account_of_other_ledger(
    client: AsyncClient, register: RegisterFn
) -> None:
    anna = await register()
    boris = await register("boris@example.com", "Борис")
    account = await create_account(client, anna)

    # Борис идёт через своё пространство, но подставляет чужой id счёта
    response = await client.patch(
        f"/api/ledgers/{boris.ledger_id}/accounts/{account['id']}",
        json={"name": "Моё"},
        headers=boris.headers,
    )
    assert response.status_code == 404


async def test_member_cannot_create_account(
    client: AsyncClient, session: AsyncSession, register: RegisterFn
) -> None:
    anna = await register()
    boris = await register("boris@example.com", "Борис")
    session.add(LedgerMember(ledger_id=anna.ledger_id, user_id=boris.id))
    await session.commit()

    response = await client.post(
        f"/api/ledgers/{anna.ledger_id}/accounts", json={"name": "Х"}, headers=boris.headers
    )
    assert response.status_code == 403


async def test_template_categories_listed_in_order(
    client: AsyncClient, register: RegisterFn
) -> None:
    anna = await register()
    result = await groups(client, anna)
    assert [g["name"] for g in result] == ["Доходы", "Базовые", "Текущие", "Крупные"]
    assert result[1]["categories"][0]["name"] == "Продукты"


async def test_duplicate_category_name_conflicts(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    group = (await groups(client, anna))[1]
    response = await client.post(
        f"/api/ledgers/{anna.ledger_id}/categories",
        json={"category_group_id": group["id"], "name": "Продукты"},
        headers=anna.headers,
    )
    assert response.status_code == 409


async def test_category_cannot_move_to_other_type(
    client: AsyncClient, register: RegisterFn
) -> None:
    anna = await register()
    income, expense = (await groups(client, anna))[:2]
    response = await client.patch(
        f"/api/ledgers/{anna.ledger_id}/categories/{expense['categories'][0]['id']}",
        json={"category_group_id": income["id"]},
        headers=anna.headers,
    )
    assert response.status_code == 422


async def test_group_with_categories_cannot_be_deleted(
    client: AsyncClient, register: RegisterFn
) -> None:
    anna = await register()
    group = (await groups(client, anna))[0]
    response = await client.delete(
        f"/api/ledgers/{anna.ledger_id}/category-groups/{group['id']}", headers=anna.headers
    )
    assert response.status_code == 409


async def test_create_group_and_category(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    base = f"/api/ledgers/{anna.ledger_id}"
    group = await client.post(
        f"{base}/category-groups", json={"name": "Хобби", "type": "expense"}, headers=anna.headers
    )
    assert group.status_code == 201
    assert group.json()["categories"] == []

    category = await client.post(
        f"{base}/categories",
        json={"category_group_id": group.json()["id"], "name": "Гитара"},
        headers=anna.headers,
    )
    assert category.status_code == 201


async def test_category_limit_set_and_cleared(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    category = (await groups(client, anna))[1]["categories"][0]
    url = f"/api/ledgers/{anna.ledger_id}/categories/{category['id']}"

    response = await client.patch(url, json={"monthly_limit": "25000"}, headers=anna.headers)
    assert Decimal(response.json()["monthly_limit"]) == 25000
    assert (await client.patch(url, json={"monthly_limit": "0"}, headers=anna.headers)).status_code == 422
    response = await client.patch(url, json={"monthly_limit": None}, headers=anna.headers)
    assert response.json()["monthly_limit"] is None
