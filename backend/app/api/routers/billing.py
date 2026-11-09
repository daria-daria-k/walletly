from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentUser, SessionDep
from app.models.enums import PaymentStatus
from app.services import billing, yookassa

router = APIRouter(prefix="/billing", tags=["billing"])


class PlanInfo(BaseModel):
    price: Decimal
    period_days: int
    payments_enabled: bool


class CheckoutResponse(BaseModel):
    confirmation_url: str


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    status: PaymentStatus
    paid_at: datetime | None
    created_at: datetime


@router.get("/plan")
async def plan_info(_: CurrentUser) -> PlanInfo:
    return PlanInfo(
        price=billing.premium_price(),
        period_days=billing.PERIOD.days,
        payments_enabled=yookassa.is_configured(),
    )


@router.post("/checkout")
async def checkout(user: CurrentUser, session: SessionDep) -> CheckoutResponse:
    return CheckoutResponse(confirmation_url=await billing.start_checkout(session, user))


@router.get("/payments")
async def payments(user: CurrentUser, session: SessionDep) -> list[PaymentRead]:
    return [PaymentRead.model_validate(item) for item in await billing.list_payments(session, user.id)]


@router.post("/payments/{payment_id}/sync")
async def sync(payment_id: int, user: CurrentUser, session: SessionDep) -> PaymentRead:
    # Нужно при возврате со страницы оплаты: уведомление может прийти позже пользователя
    return PaymentRead.model_validate(await billing.sync_payment(session, user.id, payment_id))


@router.post("/yookassa/webhook", status_code=status.HTTP_200_OK)
async def yookassa_webhook(session: SessionDep, payload: dict[str, Any] = Body()) -> None:
    # Отвечаем 200 на всё, что не смогли разобрать: иначе ЮKassa будет повторять запрос сутки.
    # Из тела берём только номер платежа, статус сервис запросит у ЮKassa сам
    provider_id = (payload.get("object") or {}).get("id")
    if isinstance(provider_id, str):
        await billing.handle_webhook(session, provider_id)
