"""Защита от перебора, перегрузки и значений, которые не принимает база."""

import logging

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.limits import BusyLimiter
from app.main import app
from app.services import auth as auth_service
from app.services import mailer

pytestmark = pytest.mark.anyio

FORGOT = "/api/auth/forgot-password"


def from_ip(ip: str) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, client=(ip, 1)), base_url="http://test")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    outbox: list[str] = []

    async def fake_send(to: str, subject: str, body: str) -> None:
        outbox.append(subject)

    monkeypatch.setattr(mailer, "send_mail", fake_send)
    return outbox


async def test_registration_is_limited_per_address(client: AsyncClient, sent: list[str]) -> None:
    body = {"password": "s3cret-pass", "name": "Б"}
    for i in range(10):
        response = await client.post("/api/auth/register", json=body | {"email": f"u{i}@example.com"})
        assert response.status_code == 201
    response = await client.post("/api/auth/register", json=body | {"email": "last@example.com"})
    assert response.status_code == 429
    async with from_ip("10.0.0.2") as other:
        response = await other.post("/api/auth/register", json=body | {"email": "other@example.com"})
    assert response.status_code == 201


async def test_stranger_cannot_use_up_owner_reset_emails(client: AsyncClient, register, sent: list[str]) -> None:
    await register("victim@example.com")
    sent.clear()
    async with from_ip("10.0.0.9") as stranger:
        for _ in range(5):
            await stranger.post(FORGOT, json={"email": "victim@example.com"})
    assert len(sent) == 3
    await client.post(FORGOT, json={"email": "victim@example.com"})
    assert len(sent) == 4


async def test_reset_emails_to_one_address_are_limited_overall(client: AsyncClient, register, sent: list[str]) -> None:
    await register("victim@example.com")
    sent.clear()
    for i in range(15):
        async with from_ip(f"10.0.1.{i}") as other:
            await other.post(FORGOT, json={"email": "victim@example.com"})
    assert len(sent) == 10


async def test_reset_requests_from_one_address_are_limited(client: AsyncClient, register, sent: list[str]) -> None:
    await register("victim@example.com")
    for i in range(20):
        await client.post(FORGOT, json={"email": f"x{i}@example.com"})
    sent.clear()
    await client.post(FORGOT, json={"email": "victim@example.com"})
    assert sent == []


async def test_login_answers_503_when_password_hashing_is_saturated(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    limiter = BusyLimiter(1, 0.01, "занято")
    monkeypatch.setattr(auth_service, "_argon", limiter)
    async with limiter.slot():
        response = await client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": "s3cret-pass"}
        )
    assert response.status_code == 503


@pytest.mark.parametrize("secret", ["change-me", "x" * 31])
def test_weak_jwt_secret_stops_startup(secret: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(jwt_secret=secret)


def test_strong_jwt_secret_is_accepted() -> None:
    assert Settings(jwt_secret="x" * 32).jwt_secret == "x" * 32


@pytest.mark.parametrize(
    ("production", "leaks"), [(True, False), (False, True)], ids=["server", "local"]
)
async def test_reset_link_reaches_log_only_locally(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, production: bool, leaks: bool
) -> None:
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "cookie_secure", production)
    with caplog.at_level(logging.WARNING):
        await mailer.send_mail("a@example.com", "Сброс", "token=secret-token")
    assert ("secret-token" in caplog.text) is leaks


async def test_values_rejected_by_database_are_client_errors(client: AsyncClient, register) -> None:
    anna = await register()
    base = f"/api/ledgers/{anna.ledger_id}"
    account = await client.post(f"{base}/accounts", json={"name": "Карта"}, headers=anna.headers)
    good = {"type": "expense", "amount": "1", "account_id": account.json()["id"], "tx_date": "2026-11-01"}
    huge = 99999999999999999999
    cases = [
        ("POST", f"{base}/transactions", good | {"description": "a\u0000b"}),
        ("POST", f"{base}/transactions", good | {"account_id": huge}),
        ("POST", f"{base}/accounts", {"name": "a\u0000b"}),
        ("POST", f"{base}/accounts", {"name": "Х", "sort_order": 3000000000}),
        ("GET", f"{base}/transactions?offset={huge}", None),
        ("GET", f"{base}/transactions?search=a%00b", None),
        ("GET", f"/api/ledgers/{huge}", None),
        ("PATCH", "/api/auth/me", {"name": "a\u0000b"}),
    ]
    for method, url, body in cases:
        kwargs = {"json": body} if body is not None else {}
        response = await client.request(method, url, headers=anna.headers, **kwargs)
        assert 400 <= response.status_code < 500, (url, body, response.status_code)


async def test_registration_with_nul_is_client_error(client: AsyncClient, sent: list[str]) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "n@example.com", "password": "s3cret-pass", "name": "a\u0000b"},
    )
    assert response.status_code == 422
