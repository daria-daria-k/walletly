from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import InvitationStatus
from app.schemas.auth import NormalizedEmail


class InvitationCreate(BaseModel):
    email: NormalizedEmail


class InvitationRead(BaseModel):
    """Для управляющих пространством. token нужен, чтобы показать ссылку: почты пока нет."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    token: str
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime


class InvitationPreview(BaseModel):
    ledger_name: str
    invited_email: str
    status: InvitationStatus
    expires_at: datetime
