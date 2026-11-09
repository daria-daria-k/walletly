from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Plan, UserRole


class WeekCount(BaseModel):
    week_start: date
    count: int


class AdminStats(BaseModel):
    users_total: int
    users_active: int
    users_premium: int
    users_new_30d: int
    transactions_total: int
    registrations: list[WeekCount]


class AuditEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_email: str
    target_email: str
    action: str
    detail: str
    created_at: datetime


class AdminUserRead(BaseModel):
    id: int
    email: str
    name: str
    role: UserRole
    is_active: bool
    plan: Plan
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUserRead]
    total: int


class AdminUserUpdate(BaseModel):
    is_active: bool = Field(default=None)
    role: UserRole = Field(default=None)
    plan: Plan = Field(default=None)
