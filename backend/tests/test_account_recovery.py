"""Лимиты входа, сброс пароля и подтверждение email."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailToken, RefreshToken
from app.services import mailer
from app.services.auth import delete_stale_tokens

pytestmark = pytest.mark.anyio


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Письма складываем в список: из него тест достаёт ссылку, как пользователь из почты."""
    outbox: list[tuple[str, str, str]] = []

    async def fake_send(to: str, subject: str, body: str) -> None:
        outbox.append((to, subject, body))

    monkeypatch.setattr(mailer, "send_mail", fake_send)
    return outbox


def token_from(mail: tuple[str, str, str]) -> str:
    return mail[2].split("token=")[1].split()[0]


async def test_login_blocked_after_too_many_failures(client: AsyncClient, register) -> None:
    await register("a@example.com")
    bad = {"email": "a@example.com", "password": "wrong-pass"}
    for _ in range(10):
        assert (await client.post("/api/auth/login", json=bad)).status_code == 401

    blocked = await client.post("/api/auth/login", json=bad)
    assert blocked.status_code == 429
    # Даже верный пароль не проходит: иначе подбор можно было бы продолжать
    good = {"email": "a@example.com", "password": "s3cret-pass"}
    assert (await client.post("/api/auth/login", json=good)).status_code == 429


async def test_successful_login_resets_counter(client: AsyncClient, register) -> None:
    await register("a@example.com")
    bad = {"email": "a@example.com", "password": "wrong-pass"}
    good = {"email": "a@example.com", "password": "s3cret-pass"}
    for _ in range(9):
        await client.post("/api/auth/login", json=bad)
    assert (await client.post("/api/auth/login", json=good)).status_code == 200
    for _ in range(9):
        assert (await client.post("/api/auth/login", json=bad)).status_code == 401


async def test_forgot_password_same_answer_for_unknown_email(client: AsyncClient, register, sent) -> None:
    await register("a@example.com")
    sent.clear()
    known = await client.post("/api/auth/forgot-password", json={"email": "a@example.com"})
    unknown = await client.post("/api/auth/forgot-password", json={"email": "no@example.com"})
    assert known.status_code == unknown.status_code == 204
    assert [mail[0] for mail in sent] == ["a@example.com"]


async def test_reset_password_changes_it_and_ends_sessions(
    client: AsyncClient, register, sent, session: AsyncSession
) -> None:
    user = await register("a@example.com")
    sent.clear()
    await client.post("/api/auth/forgot-password", json={"email": "a@example.com"})
    token = token_from(sent[0])

    response = await client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "brand-new-pass"}
    )
    assert response.status_code == 204

    old = {"email": "a@example.com", "password": "s3cret-pass"}
    new = {"email": "a@example.com", "password": "brand-new-pass"}
    assert (await client.post("/api/auth/login", json=old)).status_code == 401
    assert (await client.post("/api/auth/login", json=new)).status_code == 200

    tokens = (await session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))).all()
    # Сессия, открытая до сброса, отозвана; действует только новый вход
    assert sum(1 for item in tokens if item.revoked_at is None) == 1


async def test_reset_token_works_once(client: AsyncClient, register, sent) -> None:
    await register("a@example.com")
    sent.clear()
    await client.post("/api/auth/forgot-password", json={"email": "a@example.com"})
    payload = {"token": token_from(sent[0]), "new_password": "brand-new-pass"}
    assert (await client.post("/api/auth/reset-password", json=payload)).status_code == 204
    assert (await client.post("/api/auth/reset-password", json=payload)).status_code == 400


async def test_new_reset_request_cancels_previous_link(client: AsyncClient, register, sent) -> None:
    await register("a@example.com")
    sent.clear()
    await client.post("/api/auth/forgot-password", json={"email": "a@example.com"})
    await client.post("/api/auth/forgot-password", json={"email": "a@example.com"})
    first = {"token": token_from(sent[0]), "new_password": "brand-new-pass"}
    second = {"token": token_from(sent[1]), "new_password": "brand-new-pass"}
    assert (await client.post("/api/auth/reset-password", json=first)).status_code == 400
    assert (await client.post("/api/auth/reset-password", json=second)).status_code == 204


async def test_expired_reset_token_rejected(
    client: AsyncClient, register, sent, session: AsyncSession
) -> None:
    await register("a@example.com")
    sent.clear()
    await client.post("/api/auth/forgot-password", json={"email": "a@example.com"})
    stored = (await session.scalars(select(EmailToken))).all()
    for item in stored:
        item.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.commit()
    payload = {"token": token_from(sent[0]), "new_password": "brand-new-pass"}
    assert (await client.post("/api/auth/reset-password", json=payload)).status_code == 400


async def test_forgot_password_is_limited(client: AsyncClient, register, sent) -> None:
    await register("a@example.com")
    sent.clear()
    for _ in range(6):
        await client.post("/api/auth/forgot-password", json={"email": "a@example.com"})
    # Ответ тот же, но чужой ящик нельзя завалить письмами
    assert len(sent) == 3


async def test_email_verification(client: AsyncClient, sent) -> None:
    credentials = {"email": "b@example.com", "password": "s3cret-pass"}
    await client.post("/api/auth/register", json=credentials | {"name": "Б"})
    assert len(sent) == 1

    login = await client.post("/api/auth/login", json=credentials)
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get("/api/auth/me", headers=headers)).json()["email_verified_at"] is None

    response = await client.post("/api/auth/verify-email", json={"token": token_from(sent[0])})
    assert response.status_code == 204
    assert (await client.get("/api/auth/me", headers=headers)).json()["email_verified_at"] is not None


async def test_reset_token_is_not_valid_for_verification(client: AsyncClient, register, sent) -> None:
    await register("a@example.com")
    sent.clear()
    await client.post("/api/auth/forgot-password", json={"email": "a@example.com"})
    response = await client.post("/api/auth/verify-email", json={"token": token_from(sent[0])})
    assert response.status_code == 400


async def test_stale_tokens_are_deleted(client: AsyncClient, register, session: AsyncSession) -> None:
    user = await register("a@example.com")
    tokens = (await session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))).all()
    assert len(tokens) == 1
    tokens[0].expires_at = datetime.now(UTC) - timedelta(days=1)
    await session.commit()

    assert await delete_stale_tokens(session) == 1
    assert (await session.scalars(select(RefreshToken))).all() == []
