import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import Category, CategoryGroup, Ledger, LedgerMember, Subscription, User
from app.models.enums import LedgerType, MemberRole, Plan
from app.services.category_template import DEFAULT_CATEGORY_GROUPS

pytestmark = pytest.mark.anyio

VALID = {"email": "Anna@Example.com", "password": "s3cret-pass", "name": "  Анна  "}


async def test_register_returns_user_without_password(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json=VALID)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "anna@example.com"  # приведён к нижнему регистру
    assert body["name"] == "Анна"  # пробелы по краям обрезаны
    assert body["role"] == "user"
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_creates_personal_workspace(
    client: AsyncClient, session: AsyncSession
) -> None:
    await client.post("/auth/register", json=VALID)

    user = await session.scalar(select(User))
    assert verify_password("s3cret-pass", user.password_hash)

    ledger = await session.scalar(select(Ledger))
    assert (ledger.type, ledger.owner_id) == (LedgerType.PERSONAL, user.id)

    member = await session.scalar(select(LedgerMember))
    assert (member.user_id, member.ledger_id, member.role) == (user.id, ledger.id, MemberRole.OWNER)

    subscription = await session.scalar(select(Subscription))
    assert (subscription.user_id, subscription.plan) == (user.id, Plan.FREE)

    groups = (await session.scalars(select(CategoryGroup).order_by(CategoryGroup.sort_order))).all()
    assert [g.name for g in groups] == [name for name, _, _ in DEFAULT_CATEGORY_GROUPS]
    assert all(g.ledger_id == ledger.id for g in groups)

    categories_count = await session.scalar(
        select(func.count()).select_from(Category).where(Category.ledger_id == ledger.id)
    )
    assert categories_count == sum(len(names) for _, _, names in DEFAULT_CATEGORY_GROUPS)


async def test_duplicate_email_in_other_case_rejected(client: AsyncClient) -> None:
    await client.post("/auth/register", json=VALID)

    response = await client.post("/auth/register", json=VALID | {"email": "ANNA@example.COM"})

    assert response.status_code == 409


@pytest.mark.parametrize(
    "override",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"name": "   "},  # из одних пробелов — после обрезки пустая строка
        {"name": ""},
    ],
)
async def test_invalid_data_rejected(client: AsyncClient, override: dict) -> None:
    response = await client.post("/auth/register", json=VALID | override)

    assert response.status_code == 422
