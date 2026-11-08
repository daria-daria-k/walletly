import io
from datetime import date

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from tests.conftest import AuthedUser, RegisterFn

pytestmark = pytest.mark.anyio

HEADER = "Дата;Тип;Сумма;Счёт;Счёт зачисления;Категория;Описание\n"
GOOD = (
    "01.10.2026;расход;1 500,50;Сбер;;Продукты;Магазин\n"
    "02.10.2026;доход;10000;Сбер;;Зарплата;\n"
    "03.10.2026;перевод;200;Сбер;Наличные;;\n"
)


@pytest.fixture
async def anna(client: AsyncClient, register: RegisterFn) -> AuthedUser:
    user = await register()
    url = f"/api/ledgers/{user.ledger_id}/accounts"
    for name in ("Сбер", "Наличные"):
        await client.post(url, json={"name": name}, headers=user.headers)
    return user


async def upload(
    client: AsyncClient, user: AuthedUser, text: str, name: str = "bank.csv", **params
):
    return await client.post(
        f"/api/ledgers/{user.ledger_id}/import",
        files={"file": (name, text.encode())},
        params=params,
        headers=user.headers,
    )


async def tx_total(client: AsyncClient, user: AuthedUser) -> int:
    page = await client.get(f"/api/ledgers/{user.ledger_id}/transactions", headers=user.headers)
    return page.json()["total"]


async def test_csv_import_creates_operations(client: AsyncClient, anna: AuthedUser) -> None:
    response = await upload(client, anna, HEADER + GOOD)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "total_rows": 3,
        "created": 3,
        "skipped_duplicates": 0,
        "errors": [],
        "dry_run": False,
    }
    accounts = await client.get(f"/api/ledgers/{anna.ledger_id}/accounts", headers=anna.headers)
    assert {a["name"]: a["balance"] for a in accounts.json()} == {
        "Сбер": "8299.50",
        "Наличные": "200.00",
    }


async def test_xlsx_import(client: AsyncClient, anna: AuthedUser) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Дата", "Сумма", "Счёт", "Категория"])
    sheet.append(["05.10.2026", -99.9, "сбер", "продукты"])  # float и другой регистр
    sheet.append([date(2026, 10, 6), -50, "Сбер", "Продукты"])  # настоящая дата Excel
    sheet.append(["07.10.2026", 70, "Сбер", "Продукты"])  # без типа плюс — это доход
    buffer = io.BytesIO()
    workbook.save(buffer)
    url = f"/api/ledgers/{anna.ledger_id}/import"
    files = {"file": ("bank.xlsx", buffer.getvalue())}

    response = await client.post(url, files=files, headers=anna.headers)
    assert response.json()["errors"] == [{"row": 4, "message": "Категория «Продукты» не найдена"}]

    sheet.delete_rows(4)
    buffer = io.BytesIO()
    workbook.save(buffer)
    response = await client.post(
        url, files={"file": ("bank.xlsx", buffer.getvalue())}, headers=anna.headers
    )
    assert response.json()["created"] == 2
    accounts = await client.get(f"/api/ledgers/{anna.ledger_id}/accounts", headers=anna.headers)
    assert accounts.json()[0]["balance"] == "-149.90"


async def test_dry_run_saves_nothing(client: AsyncClient, anna: AuthedUser) -> None:
    response = await upload(client, anna, HEADER + GOOD, dry_run=True)
    assert response.json()["created"] == 3
    assert await tx_total(client, anna) == 0


async def test_any_error_cancels_whole_file(client: AsyncClient, anna: AuthedUser) -> None:
    bad = "04.10.2026;расход;100;Нет такого;;Продукты;\n"
    response = await upload(client, anna, HEADER + GOOD + bad)
    assert response.json()["errors"] == [{"row": 5, "message": "Счёт «Нет такого» не найден"}]
    assert response.json()["created"] == 0
    assert await tx_total(client, anna) == 0


async def test_reupload_is_idempotent(client: AsyncClient, anna: AuthedUser) -> None:
    await upload(client, anna, HEADER + GOOD)
    response = await upload(client, anna, HEADER + GOOD)
    assert response.json()["created"] == 0
    assert response.json()["skipped_duplicates"] == 3
    assert await tx_total(client, anna) == 3


async def test_identical_rows_in_one_file_are_kept(client: AsyncClient, anna: AuthedUser) -> None:
    coffee = "01.10.2026;расход;200;Сбер;;Кафе и рестораны;Кофе\n"
    response = await upload(client, anna, HEADER + coffee * 2)
    assert response.json()["created"] == 2

    # В новой выписке кофе уже три: две покупки есть, добавится только третья
    response = await upload(client, anna, HEADER + coffee * 3)
    assert (response.json()["created"], response.json()["skipped_duplicates"]) == (1, 2)


@pytest.mark.parametrize(
    "cells",
    [
        "не дата;расход;100;Сбер;;Продукты;",
        "01.10.2026;расход;abc;Сбер;;Продукты;",
        "01.10.2026;расход;NaN;Сбер;;Продукты;",
        "01.10.2026;расход;1.999;Сбер;;Продукты;",
        "01.10.2026;расход;0;Сбер;;Продукты;",
        "01.10.2026;бонус;100;Сбер;;Продукты;",
        "01.10.2026;расход;100;Сбер;;Зарплата;",
    ],
)
async def test_bad_rows_reported(client: AsyncClient, anna: AuthedUser, cells: str) -> None:
    response = await upload(client, anna, HEADER + cells + "\n")
    assert response.status_code == 200
    assert len(response.json()["errors"]) == 1


async def test_wrong_format_and_columns_rejected(client: AsyncClient, anna: AuthedUser) -> None:
    assert (await upload(client, anna, "x", name="a.pdf")).status_code == 422
    assert (await upload(client, anna, "Что-то;Другое\n1;2\n")).status_code == 422
    assert (await upload(client, anna, "garbage", name="a.xlsx")).status_code == 422
    assert (await upload(client, anna, "")).status_code == 422


async def test_stranger_cannot_import(
    client: AsyncClient, anna: AuthedUser, register: RegisterFn
) -> None:
    boris = await register("boris@example.com", "Борис")
    response = await client.post(
        f"/api/ledgers/{anna.ledger_id}/import",
        files={"file": ("a.csv", b"x")},
        headers=boris.headers,
    )
    assert response.status_code == 404
