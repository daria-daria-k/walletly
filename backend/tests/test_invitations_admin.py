from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invitation, User
from app.models.enums import UserRole
from tests.conftest import AuthedUser, RegisterFn

pytestmark = pytest.mark.anyio


async def family(client: AsyncClient, owner: AuthedUser) -> int:
    response = await client.post("/api/ledgers", json={"name": "Семья"}, headers=owner.headers)
    return response.json()["id"]


async def invite(client: AsyncClient, owner: AuthedUser, ledger_id: int, email: str):
    return await client.post(
        f"/api/ledgers/{ledger_id}/invitations", json={"email": email}, headers=owner.headers
    )


@pytest.fixture
async def anna(register: RegisterFn) -> AuthedUser:
    return await register()


@pytest.fixture
async def boris(register: RegisterFn) -> AuthedUser:
    return await register("boris@example.com", "Борис")


async def test_accept_adds_member(client: AsyncClient, anna: AuthedUser, boris: AuthedUser) -> None:
    family_id = await family(client, anna)
    token = (await invite(client, anna, family_id, "Boris@Example.com")).json()["token"]

    preview = await client.get(f"/api/invitations/{token}", headers=boris.headers)
    assert preview.json()["ledger_name"] == "Семья"

    accepted = await client.post(f"/api/invitations/{token}/accept", headers=boris.headers)
    assert accepted.json() == {"ledger_id": family_id}
    ledgers = (await client.get("/api/ledgers", headers=boris.headers)).json()
    assert {(item["id"], item["role"]) for item in ledgers} >= {(family_id, "member")}

    again = await client.post(f"/api/invitations/{token}/accept", headers=boris.headers)
    assert again.status_code == 409


async def test_other_email_cannot_accept(
    client: AsyncClient, anna: AuthedUser, boris: AuthedUser
) -> None:
    family_id = await family(client, anna)
    token = (await invite(client, anna, family_id, "vera@example.com")).json()["token"]
    response = await client.post(f"/api/invitations/{token}/accept", headers=boris.headers)
    assert response.status_code == 403


async def test_expired_invitation_rejected(
    client: AsyncClient, session: AsyncSession, anna: AuthedUser, boris: AuthedUser
) -> None:
    family_id = await family(client, anna)
    token = (await invite(client, anna, family_id, "boris@example.com")).json()["token"]
    await session.execute(
        update(Invitation).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await session.commit()

    response = await client.post(f"/api/invitations/{token}/accept", headers=boris.headers)
    assert response.status_code == 409
    listed = await client.get(f"/api/ledgers/{family_id}/invitations", headers=anna.headers)
    assert listed.json()[0]["status"] == "expired"


async def test_duplicates_and_personal_ledger_rejected(
    client: AsyncClient, anna: AuthedUser
) -> None:
    family_id = await family(client, anna)
    assert (await invite(client, anna, family_id, "x@example.com")).status_code == 201
    assert (await invite(client, anna, family_id, "x@example.com")).status_code == 409
    assert (await invite(client, anna, family_id, "anna@example.com")).status_code == 409
    assert (await invite(client, anna, anna.ledger_id, "x@example.com")).status_code == 409


async def test_decline_and_revoke(
    client: AsyncClient, anna: AuthedUser, boris: AuthedUser
) -> None:
    family_id = await family(client, anna)
    token = (await invite(client, anna, family_id, "boris@example.com")).json()["token"]
    declined = await client.post(f"/api/invitations/{token}/decline", headers=boris.headers)
    assert declined.status_code == 204

    other = (await invite(client, anna, family_id, "boris@example.com")).json()
    url = f"/api/ledgers/{family_id}/invitations/{other['id']}"
    assert (await client.delete(url, headers=anna.headers)).status_code == 204
    gone = await client.post(f"/api/invitations/{other['token']}/accept", headers=boris.headers)
    assert gone.status_code == 404


# --- Администрирование ---


async def make_admin(session: AsyncSession, user: AuthedUser) -> None:
    await session.execute(update(User).where(User.id == user.id).values(role=UserRole.ADMIN))
    await session.commit()


async def test_admin_api_closed_for_regular_user(client: AsyncClient, anna: AuthedUser) -> None:
    assert (await client.get("/api/admin/stats", headers=anna.headers)).status_code == 403


async def test_admin_lists_and_searches_users(
    client: AsyncClient, session: AsyncSession, anna: AuthedUser, boris: AuthedUser
) -> None:
    await make_admin(session, anna)
    page = (await client.get("/api/admin/users", headers=anna.headers)).json()
    assert page["total"] == 2
    assert page["items"][0]["plan"] == "free"

    found = await client.get("/api/admin/users", params={"search": "бор"}, headers=anna.headers)
    assert [u["email"] for u in found.json()["items"]] == ["boris@example.com"]


async def test_block_ends_sessions(
    client: AsyncClient, session: AsyncSession, anna: AuthedUser, boris: AuthedUser
) -> None:
    await make_admin(session, anna)
    credentials = {"email": "boris@example.com", "password": "s3cret-pass"}
    refresh = (await client.post("/api/auth/login", json=credentials)).cookies["refresh_token"]
    client.cookies.clear()

    response = await client.patch(
        f"/api/admin/users/{boris.id}", json={"is_active": False}, headers=anna.headers
    )
    assert response.json()["is_active"] is False
    assert (await client.get("/api/auth/me", headers=boris.headers)).status_code == 401
    stale = await client.post("/api/auth/refresh", headers={"Cookie": f"refresh_token={refresh}"})
    assert stale.status_code == 401


async def test_admin_cannot_lock_himself_out(
    client: AsyncClient, session: AsyncSession, anna: AuthedUser
) -> None:
    await make_admin(session, anna)
    for body in ({"is_active": False}, {"role": "user"}):
        response = await client.patch(
            f"/api/admin/users/{anna.id}", json=body, headers=anna.headers
        )
        assert response.status_code == 409


async def test_plan_change_and_stats(
    client: AsyncClient, session: AsyncSession, anna: AuthedUser, boris: AuthedUser
) -> None:
    await make_admin(session, anna)
    response = await client.patch(
        f"/api/admin/users/{boris.id}", json={"plan": "premium"}, headers=anna.headers
    )
    assert response.json()["plan"] == "premium"
    stats = (await client.get("/api/admin/stats", headers=anna.headers)).json()
    assert stats == {
        "users_total": 2,
        "users_active": 2,
        "users_premium": 1,
        "transactions_total": 0,
    }
