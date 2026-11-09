from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, SessionDep
from app.models.enums import Plan
from app.schemas.admin import (
    AdminStats,
    AdminUserPage,
    AdminUserRead,
    AdminUserUpdate,
    AuditEntryRead,
)
from app.services import admin as admin_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def stats(admin: AdminUser, session: SessionDep) -> AdminStats:
    return await admin_service.stats(session)


@router.get("/users")
async def list_users(
    admin: AdminUser,
    session: SessionDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    plan: Plan | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUserPage:
    items, total = await admin_service.list_users(session, search, plan, limit, offset)
    return AdminUserPage(items=items, total=total)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int, data: AdminUserUpdate, admin: AdminUser, session: SessionDep
) -> AdminUserRead:
    return await admin_service.update_user(session, admin, user_id, data)


@router.get("/audit")
async def audit(admin: AdminUser, session: SessionDep) -> list[AuditEntryRead]:
    return [AuditEntryRead.model_validate(entry) for entry in await admin_service.audit_log(session)]
