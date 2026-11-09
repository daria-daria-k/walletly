"""Все строки вымышленные: настоящих выписок в репозитории быть не должно."""

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import statement
from tests.test_ml import _premium


def _table(*rows: list[str]) -> list[list]:
    return [[number, cells] for number, cells in enumerate(rows, start=1)]


def test_bank_is_found_in_header_only() -> None:
    text = "АО «ТБанк»\nВыписка\n" + "\n" * 30 + "Перевод в Сбербанк"
    assert statement.detect_bank(text) == "Т-Банк"
    assert statement.detect_bank("\n" * 30 + "Перевод в Сбербанк") is None


@pytest.mark.parametrize(
    ("header", "bank"),
    [
        ("ПАО Сбербанк", "Сбер"),
        ("АО «Альфа-Банк»", "Альфа-Банк"),
        ("Банк ВТБ (ПАО)", "ВТБ"),
        ("АО «Райффайзенбанк»", "Райффайзен"),
        ("АО КБ «Хлынов»", "Хлынов"),
        ("ООО «Какой-то кредит банк»", None),
    ],
)
def test_detect_bank(header: str, bank: str | None) -> None:
    assert statement.detect_bank(header) == bank


def test_amounts_before_description() -> None:
    text = "\n".join(
        [
            "01.11.2026 02.11.2026 -1 250.50 ₽ -1 250.50 ₽ Оплата в MAGAZIN 1234",
            "12:30 00:00 MOSCOW",
            "03.11.2026 03.11.2026 +5 000.00 ₽ +5 000.00 ₽ Пополнение 1234",
            "09:00 09:01",
            "04.11.2026 05.11.2026 -10.00 $ не наша валюта",
        ]
    )
    assert [(x.tx_date, x.description, x.amount) for x in statement.parse_text(text)] == [
        ("01.11.2026", "Оплата в MAGAZIN MOSCOW", Decimal("-1250.50")),
        ("03.11.2026", "Пополнение", Decimal("5000.00")),
    ]


def test_second_date_and_currency_after_amount() -> None:
    lines = statement.parse_text("2026-11-01 12:30:45 2026-11-02 Оплата такси 350,00 RUB 1 000,00 RUB")
    assert [(x.tx_date, x.description, x.amount) for x in lines] == [
        ("2026-11-01", "Оплата такси", Decimal("-350.00"))
    ]


OPERATIONS = "01.11.2026 Кофе 100,00\n02.11.2026 Зарплата +900,00\n"


def test_totals_match() -> None:
    assert statement.parse_pdf_text(OPERATIONS + "Всего пополнений 900,00\nВсего списаний 100,00").reconciled is True


def test_totals_do_not_match() -> None:
    assert statement.parse_pdf_text(OPERATIONS + "Всего пополнений 900,00\nВсего списаний 200,00").reconciled is False


def test_no_totals_to_compare() -> None:
    assert statement.parse_pdf_text(OPERATIONS).reconciled is None


def test_tbank_table_skips_failed() -> None:
    parsed = statement.parse_table(
        _table(
            ["Дата операции", "Дата платежа", "Статус", "Сумма платежа", "Описание"],
            ["01.11.2026 12:30:00", "01.11.2026", "OK", "-250,50", "Кофейня"],
            ["02.11.2026 12:30:00", "02.11.2026", "FAILED", "-999,00", "Отклонено"],
            ["03.11.2026 12:30:00", "03.11.2026", "OK", "1000,00", "Пополнение"],
        )
    )
    assert parsed is not None and parsed.bank == "Т-Банк"
    assert [(x.tx_date, x.description, x.amount) for x in parsed.lines] == [
        ("01.11.2026", "Кофейня", Decimal("-250.50")),
        ("03.11.2026", "Пополнение", Decimal("1000.00")),
    ]


def test_alfa_table_uses_income_and_expense_columns() -> None:
    parsed = statement.parse_table(
        _table(
            ["Тип счёта", "Номер счета", "Валюта", "Дата операции", "Референс проводки", "Описание операции", "Приход", "Расход", ""],
            ["Текущий", "40817", "RUR", "01.11.26", "CRD_1", "MAGAZIN", "0", "300,00", ""],
            ["Текущий", "40817", "RUR", "02.11.26", "CRD_2", "Перевод", "700,00", "0", ""],
        )
    )
    assert parsed is not None and parsed.bank == "Альфа-Банк"
    assert [x.amount for x in parsed.lines] == [Decimal("-300.00"), Decimal("700.00")]


def test_vtb_table_finds_operations_among_blocks() -> None:
    parsed = statement.parse_table(
        _table(
            ["Период"],
            ["Счёт", "40817"],
            ["40817", "2026-11-01 10:00:00", "2026-11-02 00:00:00", "-1 500,00", "RUB", "-1 500,00", "RUB", "Карта *1234 Аптека", "Исполнено"],
        )
    )
    assert parsed is not None and parsed.bank == "ВТБ"
    assert [(x.tx_date, x.description, x.amount) for x in parsed.lines] == [
        ("2026-11-01", "Аптека", Decimal("-1500.00"))
    ]


def test_template_is_not_a_bank_table() -> None:
    assert statement.parse_table(_table(["Дата", "Сумма", "Счёт"], ["01.11.2026", "10", "Карта"])) is None


def test_bad_amount_is_a_clean_error() -> None:
    with pytest.raises(statement.InvalidDataError, match="Строка 2"):
        statement.parse_table(
            _table(
                ["Дата операции", "Статус", "Сумма платежа", "Описание"],
                ["01.11.2026", "OK", "много", "x"],
            )
        )


TBANK_CSV = (
    "Дата операции;Дата платежа;Номер карты;Статус;Сумма операции;Валюта операции;"
    "Сумма платежа;Валюта платежа;Кэшбэк;Категория;MCC;Описание;Бонусы\n"
    "01.11.2026 12:30:00;01.11.2026;*1234;OK;-250,50;RUB;-250,50;RUB;;Кафе;5812;Кофейня;0\n"
).encode("cp1251")


async def _account(client: AsyncClient, user) -> int:
    url = f"/api/ledgers/{user.ledger_id}/accounts"
    return (await client.post(url, json={"name": "Карта"}, headers=user.headers)).json()["id"]


def _upload(user, params: dict) -> dict:
    return {
        "url": f"/api/ledgers/{user.ledger_id}/import",
        "params": params,
        "files": {"file": ("bank.csv", TBANK_CSV, "text/csv")},
        "headers": user.headers,
    }


@pytest.mark.anyio
async def test_bank_csv_in_windows_encoding(client: AsyncClient, register, session: AsyncSession) -> None:
    user = await register()
    await _premium(session, user.id)
    account = await _account(client, user)

    response = await client.post(**_upload(user, {"account_id": account}))

    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1 and response.json()["bank"] == "Т-Банк"
    accounts = (await client.get(f"/api/ledgers/{user.ledger_id}/accounts", headers=user.headers)).json()
    assert Decimal(accounts[0]["balance"]) == Decimal("-250.50")


@pytest.mark.anyio
async def test_bank_csv_needs_account(client: AsyncClient, register, session: AsyncSession) -> None:
    user = await register()
    await _premium(session, user.id)
    response = await client.post(**_upload(user, {}))
    assert response.status_code == 422
    assert "счёт" in response.json()["detail"]


@pytest.mark.anyio
async def test_bank_csv_needs_premium(client: AsyncClient, register) -> None:
    user = await register()
    account = await _account(client, user)
    assert (await client.post(**_upload(user, {"account_id": account}))).status_code == 403
