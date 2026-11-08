import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Ledger, LedgerMember
from app.models.enums import MemberRole
from tests.conftest import AuthedUser, RegisterFn

pytestmark = pytest.mark.anyio


async def create_family(client: AsyncClient, owner: AuthedUser) -> int:
    response = await client.post("/api/ledgers", json={"name": "Семья"}, headers=owner.headers)
    assert response.status_code == 201
    return response.json()["id"]


async def add_member(
    session: AsyncSession, ledger_id: int, user: AuthedUser, role: MemberRole = MemberRole.MEMBER
) -> None:
    session.add(LedgerMember(ledger_id=ledger_id, user_id=user.id, role=role))
    await session.commit()


async def test_new_user_has_personal_ledger(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    ledgers = (await client.get("/api/ledgers", headers=anna.headers)).json()
    assert [(item["type"], item["role"]) for item in ledgers] == [("personal", "owner")]


async def test_shared_ledger_gets_category_template(
    client: AsyncClient, session: AsyncSession, register: RegisterFn
) -> None:
    anna = await register()
    family_id = await create_family(client, anna)
    count = await session.scalar(
        select(func.count()).select_from(Category).where(Category.ledger_id == family_id)
    )
    assert count > 0


async def test_stranger_sees_404(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    boris = await register("boris@example.com", "Борис")
    response = await client.get(f"/api/ledgers/{anna.ledger_id}", headers=boris.headers)
    assert response.status_code == 404


async def test_member_cannot_rename(
    client: AsyncClient, session: AsyncSession, register: RegisterFn
) -> None:
    anna = await register()
    boris = await register("boris@example.com", "Борис")
    family_id = await create_family(client, anna)
    await add_member(session, family_id, boris)

    response = await client.patch(
        f"/api/ledgers/{family_id}", json={"name": "Наша"}, headers=boris.headers
    )
    assert response.status_code == 403


async def test_personal_ledger_cannot_be_deleted(client: AsyncClient, register: RegisterFn) -> None:
    anna = await register()
    response = await client.delete(f"/api/ledgers/{anna.ledger_id}", headers=anna.headers)
    assert response.status_code == 409


async def test_owner_deletes_shared_ledger(
    client: AsyncClient, session: AsyncSession, register: RegisterFn
) -> None:
    anna = await register()
    family_id = await create_family(client, anna)
    response = await client.delete(f"/api/ledgers/{family_id}", headers=anna.headers)
    assert response.status_code == 204
    assert await session.get(Ledger, family_id) is None


async def test_member_can_leave_but_owner_cannot(
    client: AsyncClient, session: AsyncSession, register: RegisterFn
) -> None:
    anna = await register()
    boris = await register("boris@example.com", "Борис")
    family_id = await create_family(client, anna)
    await add_member(session, family_id, boris)

    left = await client.delete(
        f"/api/ledgers/{family_id}/members/{boris.id}", headers=boris.headers
    )
    assert left.status_code == 204
    owner = await client.delete(f"/api/ledgers/{family_id}/members/{anna.id}", headers=anna.headers)
    assert owner.status_code == 409


async def test_admin_cannot_remove_admin(
    client: AsyncClient, session: AsyncSession, register: RegisterFn
) -> None:
    anna = await register()
    boris = await register("boris@example.com", "Борис")
    vera = await register("vera@example.com", "Вера")
    family_id = await create_family(client, anna)
    await add_member(session, family_id, boris, MemberRole.ADMIN)
    await add_member(session, family_id, vera, MemberRole.ADMIN)

    response = await client.delete(
        f"/api/ledgers/{family_id}/members/{vera.id}", headers=boris.headers
    )
    assert response.status_code == 403


async def test_only_owner_changes_roles(
    client: AsyncClient, session: AsyncSession, register: RegisterFn
) -> None:
    anna = await register()
    boris = await register("boris@example.com", "Борис")
    family_id = await create_family(client, anna)
    await add_member(session, family_id, boris, MemberRole.ADMIN)
    url = f"/api/ledgers/{family_id}/members/{boris.id}"

    assert (await client.patch(url, json={"role": "member"}, headers=boris.headers)).status_code == 403
    response = await client.patch(url, json={"role": "member"}, headers=anna.headers)
    assert response.json()["role"] == "member"
