import io

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook

from tests.conftest import AuthedUser, RegisterFn
from tests.test_import import GOOD, HEADER, upload

pytestmark = pytest.mark.anyio


@pytest.fixture
async def anna(client: AsyncClient, register: RegisterFn) -> AuthedUser:
    user = await register()
    url = f"/api/ledgers/{user.ledger_id}/accounts"
    for name in ("Сбер", "Наличные"):
        await client.post(url, json={"name": name}, headers=user.headers)
    return user


async def export(client: AsyncClient, user: AuthedUser, **params):
    return await client.get(
        f"/api/ledgers/{user.ledger_id}/export", params=params, headers=user.headers
    )


async def history(client: AsyncClient, user: AuthedUser) -> list[dict]:
    response = await client.get(f"/api/ledgers/{user.ledger_id}/import/history", headers=user.headers)
    return response.json()


async def test_history_records_real_upload_not_check(client: AsyncClient, anna: AuthedUser) -> None:
    await upload(client, anna, HEADER + GOOD, dry_run=True)
    assert await history(client, anna) == []

    await upload(client, anna, HEADER + GOOD)
    rows = await history(client, anna)
    assert [(r["filename"], r["created"], r["errors"]) for r in rows] == [("bank.csv", 3, 0)]


async def test_history_records_file_with_errors(client: AsyncClient, anna: AuthedUser) -> None:
    await upload(client, anna, HEADER + "01.10.2026;расход;abc;Сбер;;Продукты;\n", dry_run=True)
    rows = await history(client, anna)
    assert [(r["created"], r["errors"]) for r in rows] == [(0, 1)]
    page = await client.get(f"/api/ledgers/{anna.ledger_id}/transactions", headers=anna.headers)
    assert page.json()["total"] == 0


async def test_export_can_be_imported_back(client: AsyncClient, anna: AuthedUser) -> None:
    await upload(client, anna, HEADER + GOOD)
    response = await export(client, anna)
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]

    again = await client.post(
        f"/api/ledgers/{anna.ledger_id}/import",
        files={"file": ("export.xlsx", response.content)},
        headers=anna.headers,
    )
    assert again.json()["errors"] == []
    assert again.json()["created"] == 0
    assert again.json()["skipped_duplicates"] == 3


async def test_export_summary_and_period(client: AsyncClient, anna: AuthedUser) -> None:
    await upload(client, anna, HEADER + GOOD)
    book = load_workbook(io.BytesIO((await export(client, anna)).content))
    assert list(book["Сводка"].values)[1] == ("RUB", 10000, 1500.5, 8499.5)

    only_first = await export(client, anna, date_from="2026-10-01", date_to="2026-10-01")
    sheet = load_workbook(io.BytesIO(only_first.content))["Операции"]
    assert sheet.max_row == 2


async def test_formula_is_exported_as_text(client: AsyncClient, anna: AuthedUser) -> None:
    payload = '=HYPERLINK("http://evil.example")'
    account = (
        await client.get(f"/api/ledgers/{anna.ledger_id}/accounts", headers=anna.headers)
    ).json()[0]["id"]
    groups = (
        await client.get(f"/api/ledgers/{anna.ledger_id}/category-groups", headers=anna.headers)
    ).json()
    category = next(g for g in groups if g["type"] == "expense")["categories"][0]["id"]
    await client.post(
        f"/api/ledgers/{anna.ledger_id}/transactions",
        json={
            "type": "expense",
            "amount": "10",
            "account_id": account,
            "category_id": category,
            "description": payload,
            "tx_date": "2026-10-05",
        },
        headers=anna.headers,
    )
    sheet = load_workbook(io.BytesIO((await export(client, anna)).content))["Операции"]
    assert sheet["G2"].value == payload
    assert sheet["G2"].data_type == "s"


async def test_stranger_cannot_export(
    client: AsyncClient, anna: AuthedUser, register: RegisterFn
) -> None:
    stranger = await register("boris@example.com", "Борис")
    response = await client.get(f"/api/ledgers/{anna.ledger_id}/export", headers=stranger.headers)
    assert response.status_code in (403, 404)
