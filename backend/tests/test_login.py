from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.models import RefreshToken, User

pytestmark = pytest.mark.anyio

CREDENTIALS = {"email": "anna@example.com", "password": "s3cret-pass"}


@pytest.fixture
async def user_id(client: AsyncClient) -> int:
    response = await client.post("/api/auth/register", json=CREDENTIALS | {"name": "Анна"})
    return response.json()["id"]


async def login(client: AsyncClient) -> Response:
    return await client.post("/api/auth/login", json=CREDENTIALS)


async def refresh_with(client: AsyncClient, token: str) -> Response:
    """Refresh с конкретным токеном — как будто его предъявил другой браузер."""
    client.cookies.clear()
    return await client.post("/api/auth/refresh", headers={"Cookie": f"refresh_token={token}"})


async def active_tokens_count(session: AsyncSession) -> int:
    return await session.scalar(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    )


# --- Вход ---


async def test_login_returns_access_token_and_refresh_cookie(
    client: AsyncClient, user_id: int
) -> None:
    response = await login(client)

    assert response.status_code == 200
    body = response.json()
    assert decode_access_token(body["access_token"]) == user_id
    assert body["token_type"] == "bearer"
    assert "refresh_token" not in body  # refresh — только в cookie

    cookie_header = response.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "Path=/api/auth" in cookie_header
    assert "SameSite=strict" in cookie_header


async def test_login_email_is_case_insensitive(client: AsyncClient, user_id: int) -> None:
    response = await client.post("/api/auth/login", json=CREDENTIALS | {"email": "ANNA@example.com"})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "credentials",
    [
        CREDENTIALS | {"password": "wrong-pass"},
        CREDENTIALS | {"email": "nobody@example.com"},
    ],
)
async def test_wrong_credentials_give_same_error(
    client: AsyncClient, user_id: int, credentials: dict
) -> None:
    response = await client.post("/api/auth/login", json=credentials)

    # Одинаковый ответ — нельзя узнать, существует ли email
    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный email или пароль"


async def test_blocked_user_cannot_login(
    client: AsyncClient, session: AsyncSession, user_id: int
) -> None:
    await session.execute(update(User).values(is_active=False))
    await session.commit()

    response = await login(client)

    assert response.status_code == 403


# --- Обновление ---


async def test_refresh_rotates_token(client: AsyncClient, user_id: int) -> None:
    old_refresh = (await login(client)).cookies["refresh_token"]

    response = await refresh_with(client, old_refresh)

    assert response.status_code == 200
    assert decode_access_token(response.json()["access_token"]) == user_id
    new_refresh = response.cookies["refresh_token"]
    assert new_refresh != old_refresh


async def test_reused_refresh_token_revokes_all_sessions(
    client: AsyncClient, session: AsyncSession, user_id: int
) -> None:
    stolen = (await login(client)).cookies["refresh_token"]
    await login(client)  # вторая сессия, например с телефона
    new_refresh = (await refresh_with(client, stolen)).cookies["refresh_token"]

    # Кто-то предъявил уже использованный токен
    response = await refresh_with(client, stolen)

    assert response.status_code == 401
    assert await active_tokens_count(session) == 0
    # Даже честно полученный новый токен больше не работает
    assert (await refresh_with(client, new_refresh)).status_code == 401


async def test_expired_refresh_token_rejected(
    client: AsyncClient, session: AsyncSession, user_id: int
) -> None:
    token = (await login(client)).cookies["refresh_token"]
    await session.execute(
        update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await session.commit()

    response = await refresh_with(client, token)

    assert response.status_code == 401


async def test_refresh_rejected_for_blocked_user(
    client: AsyncClient, session: AsyncSession, user_id: int
) -> None:
    token = (await login(client)).cookies["refresh_token"]
    await session.execute(update(User).values(is_active=False))
    await session.commit()

    response = await refresh_with(client, token)

    assert response.status_code == 401


@pytest.mark.parametrize("token", [None, "made-up-token"])
async def test_refresh_without_valid_cookie_rejected(client: AsyncClient, token: str | None) -> None:
    client.cookies.clear()
    headers = {"Cookie": f"refresh_token={token}"} if token else {}

    response = await client.post("/api/auth/refresh", headers=headers)

    assert response.status_code == 401
    assert 'refresh_token=""' in response.headers["set-cookie"]  # cookie удаляется


# --- Выход ---


async def test_logout_revokes_refresh_token(
    client: AsyncClient, session: AsyncSession, user_id: int
) -> None:
    token = (await login(client)).cookies["refresh_token"]

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert 'refresh_token=""' in response.headers["set-cookie"]
    assert await active_tokens_count(session) == 0
    assert (await refresh_with(client, token)).status_code == 401
