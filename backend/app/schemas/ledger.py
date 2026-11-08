from datetime import datetime

from pydantic import BaseModel

from app.models.enums import LedgerType, MemberRole
from app.schemas.common import Name100


class LedgerCreate(BaseModel):
    name: Name100


class LedgerRead(BaseModel):
    id: int
    name: str
    type: LedgerType
    owner_id: int
    created_at: datetime
    role: MemberRole  # роль текущего пользователя в этом пространстве


class MemberRead(BaseModel):
    user_id: int
    name: str
    email: str
    role: MemberRole
    joined_at: datetime


class MemberRoleUpdate(BaseModel):
    role: MemberRole
