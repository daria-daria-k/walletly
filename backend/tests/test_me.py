import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import User
from tests.conftest import RegisterFn

pytestmark = pytest.mark.anyio


async def test_me_returns_current_user(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    response = await client.get("/api/auth/me", headers=anna.headers)
    assert response.status_code == 200
    assert response.json()["id"] == anna.id
    assert response.json()["plan"] == "free"


async def test_me_without_token_is_unauthorized(client: AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_me_with_garbage_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


async def test_blocked_user_loses_access_immediately(
    client: AsyncClient, session: AsyncSession, register: RegisterFn
) -> None:
    anna = await register()
    await session.execute(update(User).where(User.id == anna.id).values(is_active=False))
    await session.commit()

    assert (await client.get("/api/auth/me", headers=anna.headers)).status_code == 401


async def test_token_of_deleted_user_is_unauthorized(client: AsyncClient) -> None:
    headers = {"Authorization": f"Bearer {create_access_token(999)}"}
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 401


async def test_update_name(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    response = await client.patch("/api/auth/me", json={"name": " Аня "}, headers=anna.headers)
    assert response.json()["name"] == "Аня"


async def test_change_password_ends_other_sessions(
    client: AsyncClient, register: RegisterFn
) -> None:
    anna = await register()
    credentials = {"email": "anna@example.com", "password": "s3cret-pass"}
    old_refresh = (await client.post("/api/auth/login", json=credentials)).cookies["refresh_token"]
    client.cookies.clear()

    response = await client.post(
        "/api/auth/change-password",
        json={"current_password": "s3cret-pass", "new_password": "new-s3cret-pass"},
        headers=anna.headers,
    )
    assert response.status_code == 200
    client.cookies.clear()

    stale = await client.post(
        "/api/auth/refresh", headers={"Cookie": f"refresh_token={old_refresh}"}
    )
    assert stale.status_code == 401
    assert (await client.post("/api/auth/login", json=credentials)).status_code == 401


async def test_change_password_requires_current(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    response = await client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-pass", "new_password": "new-s3cret-pass"},
        headers=anna.headers,
    )
    assert response.status_code == 400
