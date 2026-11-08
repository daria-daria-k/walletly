from fastapi import APIRouter, status

from app.api.deps import ManagerMembership, Membership, SessionDep
from app.schemas.category import (
    CategoryCreate,
    CategoryGroupCreate,
    CategoryGroupRead,
    CategoryGroupUpdate,
    CategoryRead,
    CategoryUpdate,
)
from app.services import category as category_service

router = APIRouter(prefix="/ledgers/{ledger_id}", tags=["categories"])


@router.get("/category-groups")
async def list_groups(member: Membership, session: SessionDep) -> list[CategoryGroupRead]:
    groups = await category_service.list_groups(session, member.ledger_id)
    return [CategoryGroupRead.model_validate(group) for group in groups]


@router.post("/category-groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    data: CategoryGroupCreate, member: ManagerMembership, session: SessionDep
) -> CategoryGroupRead:
    group = await category_service.create_group(session, member.ledger_id, data)
    return CategoryGroupRead.model_validate(group)


@router.patch("/category-groups/{group_id}")
async def update_group(
    group_id: int, data: CategoryGroupUpdate, member: ManagerMembership, session: SessionDep
) -> CategoryGroupRead:
    group = await category_service.update_group(session, member.ledger_id, group_id, data)
    return CategoryGroupRead.model_validate(group)


@router.delete("/category-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: int, member: ManagerMembership, session: SessionDep) -> None:
    await category_service.delete_group(session, member.ledger_id, group_id)


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryCreate, member: ManagerMembership, session: SessionDep
) -> CategoryRead:
    category = await category_service.create_category(session, member.ledger_id, data)
    return CategoryRead.model_validate(category)


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: int, data: CategoryUpdate, member: ManagerMembership, session: SessionDep
) -> CategoryRead:
    category = await category_service.update_category(session, member.ledger_id, category_id, data)
    return CategoryRead.model_validate(category)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int, member: ManagerMembership, session: SessionDep) -> None:
    await category_service.delete_category(session, member.ledger_id, category_id)
