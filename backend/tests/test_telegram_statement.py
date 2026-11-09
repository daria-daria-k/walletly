from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.train import train_ledger
from app.models import Subscription, User
from app.services import statement, telegram
from tests.test_ml import _fill, _premium

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("кофе 250", (Decimal(250), "кофе")),
        ("250 кофе с собой", (Decimal(250), "кофе с собой")),
        ("такси 199,50", (Decimal("199.50"), "такси")),
        ("просто текст", None),
        ("кофе 0", None),
    ],
)
def test_parse_expense(text, expected) -> None:
    assert telegram.parse_expense(text) == expected


def _message(chat_id: int, text: str) -> dict:
    return {"message": {"chat": {"id": chat_id}, "text": text}}


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telegram, "is_configured", lambda: True)


async def _linked(client, user, session) -> None:
    await _premium(session, user.id)
    url = (await client.post("/api/telegram/link", headers=user.headers)).json()["url"]
    _, reply = await telegram.handle_update(session, _message(555, f"/start {url.split('start=')[1]}"))
    assert "подключён" in reply


async def test_free_plan_cannot_link(client: AsyncClient, register, configured) -> None:
    user = await register()
    assert (await client.post("/api/telegram/link", headers=user.headers)).status_code == 403


async def test_link_is_one_time(client: AsyncClient, register, session: AsyncSession, configured) -> None:
    user = await register()
    await _premium(session, user.id)
    url = (await client.post("/api/telegram/link", headers=user.headers)).json()["url"]
    code = url.split("start=")[1]
    await telegram.handle_update(session, _message(555, f"/start {code}"))
    _, reply = await telegram.handle_update(session, _message(777, f"/start {code}"))
    assert "устарела" in reply
    status = (await client.get("/api/telegram/status", headers=user.headers)).json()
    assert status["linked"] is True


async def test_unknown_chat_gets_no_data(session: AsyncSession) -> None:
    _, reply = await telegram.handle_update(session, _message(1, "/balance"))
    assert "не подключён" in reply


async def test_bot_records_expense(client: AsyncClient, register, session: AsyncSession, configured) -> None:
    user = await register()
    await _linked(client, user, session)
    _, mapping = await _fill(client, user)
    await train_ledger(session, user.ledger_id)

    _, reply = await telegram.handle_update(session, _message(555, "Такси домой 300"))
    assert "Записал" in reply
    rows = (
        await client.get(
            f"/api/ledgers/{user.ledger_id}/transactions",
            params={"limit": 1},
            headers=user.headers,
        )
    ).json()["items"]
    assert Decimal(rows[0]["amount"]) == 300 and rows[0]["category_id"] == mapping[2]["id"]


async def test_bot_stops_when_premium_ends(
    client: AsyncClient, register, session: AsyncSession, configured
) -> None:
    user = await register()
    await _linked(client, user, session)
    rows = (await session.scalars(select(Subscription).where(Subscription.plan == "premium"))).all()
    for row in rows:
        await session.delete(row)
    await session.commit()
    _, reply = await telegram.handle_update(session, _message(555, "/balance"))
    assert "Premium" in reply


async def test_unlink(client: AsyncClient, register, session: AsyncSession, configured) -> None:
    user = await register()
    await _linked(client, user, session)
    assert (await client.delete("/api/telegram/link", headers=user.headers)).status_code == 204
    session.expire_all()
    assert await session.scalar(select(User.telegram_chat_id).where(User.id == user.id)) is None


SAMPLE = """Выписка по счёту
Дата Описание Сумма Остаток
02.11.2026 14:32 PYATEROCHKA 1234 1 234,56 56 789,00
03.11.2026 Перевод от Анны +5 000,00 61 789,00
04.11.26 Такси 350.00
итого за период 6 584,56
"""


def test_parse_statement_lines() -> None:
    lines = statement.parse_text(SAMPLE)
    assert [(item.tx_date, item.description, item.amount) for item in lines] == [
        ("02.11.2026", "PYATEROCHKA 1234", Decimal("-1234.56")),
        ("03.11.2026", "Перевод от Анны", Decimal("5000.00")),
        ("04.11.26", "Такси", Decimal("-350.00")),
    ]


async def test_broken_pdf_is_a_clean_error(client: AsyncClient, register, session: AsyncSession) -> None:
    user = await register()
    await _premium(session, user.id)
    account = (
        await client.post(f"/api/ledgers/{user.ledger_id}/accounts", json={"name": "Карта"}, headers=user.headers)
    ).json()
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/import/statement",
        params={"account_id": account["id"]},
        files={"file": ("a.pdf", b"not a pdf", "application/pdf")},
        headers=user.headers,
    )
    assert response.status_code == 422


async def test_statement_import_uses_fallback_category(
    client: AsyncClient, register, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await register()
    await _premium(session, user.id)
    base = f"/api/ledgers/{user.ledger_id}"
    account = (await client.post(f"{base}/accounts", json={"name": "Карта"}, headers=user.headers)).json()
    monkeypatch.setattr(statement, "extract_text", lambda content: SAMPLE)

    url = f"{base}/import/statement"
    params = {"account_id": account["id"]}
    files = {"file": ("a.pdf", b"%PDF", "application/pdf")}
    check = await client.post(url, params=params | {"dry_run": True}, files=files, headers=user.headers)
    assert check.status_code == 200, check.text
    assert check.json()["created"] == 3 and check.json()["errors"] == []

    done = await client.post(url, params=params, files=files, headers=user.headers)
    assert done.json()["created"] == 3
    accounts = (await client.get(f"{base}/accounts", headers=user.headers)).json()
    assert Decimal(accounts[0]["balance"]) == Decimal("3415.44")


async def test_statement_needs_premium(client: AsyncClient, register) -> None:
    user = await register()
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/import/statement",
        params={"account_id": 1},
        files={"file": ("a.pdf", b"%PDF", "application/pdf")},
        headers=user.headers,
    )
    assert response.status_code == 403
