from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import AdminUser, SessionDep
from app.models import Payment, User
from app.models.enums import PaymentStatus, Plan
from app.schemas.admin import (
    AdminStats,
    AdminUserPage,
    AdminUserRead,
    AdminUserUpdate,
    AuditEntryRead,
)
from app.services import admin as admin_service
from app.services import ml

class AdminPayment(BaseModel):
    id: int
    email: str
    amount: Decimal
    status: PaymentStatus
    paid_at: datetime | None
    created_at: datetime


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


@router.get("/payments")
async def payments(_: AdminUser, session: SessionDep) -> list[AdminPayment]:
    rows = await session.execute(
        select(Payment, User.email).join(User).order_by(Payment.id.desc()).limit(100)
    )
    return [
        AdminPayment(
            id=item.id,
            email=email,
            amount=item.amount,
            status=item.status,
            paid_at=item.paid_at,
            created_at=item.created_at,
        )
        for item, email in rows
    ]


class AbVariant(BaseModel):
    variant: str
    decided: int
    accepted: int
    accuracy: float | None


class AbResponse(BaseModel):
    variants: list[AbVariant]
    p_value: float | None
    winner: str | None


@router.get("/ml")
async def ml_report(_: AdminUser, session: SessionDep) -> AbResponse:
    report = await ml.ab_report(session)
    return AbResponse(
        variants=[AbVariant(**vars(item)) for item in report.variants],
        p_value=report.p_value,
        winner=report.winner,
    )
