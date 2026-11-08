from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import Plan, UserRole


class AdminStats(BaseModel):
    users_total: int
    users_active: int
    users_premium: int
    transactions_total: int


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
