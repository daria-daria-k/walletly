from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentUser, SessionDep
from app.services import notification as notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str
    link: str
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationRead]
    unread: int


@router.get("")
async def list_notifications(user: CurrentUser, session: SessionDep) -> NotificationList:
    items, unread = await notification_service.list_for_user(session, user.id)
    return NotificationList(items=items, unread=unread)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all(user: CurrentUser, session: SessionDep) -> None:
    await notification_service.mark_read(session, user.id)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_one(notification_id: int, user: CurrentUser, session: SessionDep) -> None:
    await notification_service.mark_read(session, user.id, notification_id)
