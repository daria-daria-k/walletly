import pytest
from httpx import AsyncClient

from tests.conftest import AuthedUser, RegisterFn

pytestmark = pytest.mark.anyio


@pytest.fixture
async def anna(register: RegisterFn) -> AuthedUser:
    return await register()


async def test_new_user_needs_onboarding(client: AsyncClient, anna: AuthedUser) -> None:
    me = (await client.get("/api/auth/me", headers=anna.headers)).json()
    assert me["onboarding_completed"] is False
    assert me["plan_expires_at"] is None
    assert me["notifications"] == {"budget": True, "unusual": True, "weekly": True, "family": True}


async def test_patch_changes_only_passed_fields(client: AsyncClient, anna: AuthedUser) -> None:
    response = await client.patch(
        "/api/auth/me", json={"onboarding_completed": True}, headers=anna.headers
    )
    assert response.status_code == 200
    assert response.json()["onboarding_completed"] is True
    assert response.json()["name"] == "Анна"


async def test_notifications_are_saved(client: AsyncClient, anna: AuthedUser) -> None:
    body = {"notifications": {"budget": False, "unusual": True, "weekly": False, "family": True}}
    await client.patch("/api/auth/me", json=body, headers=anna.headers)
    me = (await client.get("/api/auth/me", headers=anna.headers)).json()
    assert me["notifications"]["budget"] is False
    assert me["notifications"]["unusual"] is True


async def test_null_name_rejected(client: AsyncClient, anna: AuthedUser) -> None:
    response = await client.patch("/api/auth/me", json={"name": None}, headers=anna.headers)
    assert response.status_code == 422


async def test_account_kind(client: AsyncClient, anna: AuthedUser) -> None:
    url = f"/api/ledgers/{anna.ledger_id}/accounts"
    default = (await client.post(url, json={"name": "Карта"}, headers=anna.headers)).json()
    assert default["kind"] == "card"

    created = await client.post(url, json={"name": "Вклад", "kind": "deposit"}, headers=anna.headers)
    assert created.json()["kind"] == "deposit"
    updated = await client.patch(
        f"{url}/{created.json()['id']}", json={"kind": "savings"}, headers=anna.headers
    )
    assert updated.json()["kind"] == "savings"

    wrong = await client.post(url, json={"name": "X", "kind": "crypto"}, headers=anna.headers)
    assert wrong.status_code == 422


async def test_revoke_other_sessions(client: AsyncClient, register: RegisterFn) -> None:
    user = await register()
    credentials = {"email": "anna@example.com", "password": "s3cret-pass"}

    first = await client.post("/api/auth/login", json=credentials)
    other_cookie = first.cookies["refresh_token"]
    client.cookies.clear()
    await client.post("/api/auth/login", json=credentials)

    # Первая сессия из фикстуры register, вторая и третья из этого теста
    active = await client.get("/api/auth/sessions", headers=user.headers)
    assert active.json() == {"active": 3}

    revoked = await client.post("/api/auth/sessions/revoke-others", headers=user.headers)
    assert revoked.status_code == 204
    active = await client.get("/api/auth/sessions", headers=user.headers)
    assert active.json() == {"active": 1}

    client.cookies.clear()
    client.cookies.set("refresh_token", other_cookie, path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_revoke_others_needs_cookie(client: AsyncClient, anna: AuthedUser) -> None:
    client.cookies.clear()
    response = await client.post("/api/auth/sessions/revoke-others", headers=anna.headers)
    assert response.status_code == 400
