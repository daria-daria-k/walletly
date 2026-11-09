from fastapi import APIRouter, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.services import billing, telegram
from app.services.errors import ConflictError

router = APIRouter(prefix="/telegram", tags=["telegram"])


class TelegramStatus(BaseModel):
    configured: bool
    linked: bool


class TelegramLink(BaseModel):
    url: str


@router.get("/status")
async def status_info(user: CurrentUser) -> TelegramStatus:
    return TelegramStatus(
        configured=telegram.is_configured(), linked=user.telegram_chat_id is not None
    )


@router.post("/link")
async def link(user: CurrentUser, session: SessionDep) -> TelegramLink:
    await billing.require_premium(session, user.id, "Telegram-бот")
    if not telegram.is_configured():
        raise ConflictError("Бот пока не настроен")
    return TelegramLink(url=await telegram.create_link_url(user.id))


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
async def unlink(user: CurrentUser, session: SessionDep) -> None:
    await telegram.unlink(session, user)
