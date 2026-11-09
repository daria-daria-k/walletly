"""Тонкий клиент API ЮKassa: только два запроса, которые нужны приложению."""

from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.core.config import settings
from app.services.errors import ConflictError

_API = "https://api.yookassa.ru/v3"


@dataclass(frozen=True)
class ProviderPayment:
    id: str
    status: str  # pending, waiting_for_capture, succeeded, canceled
    paid: bool
    amount: Decimal
    confirmation_url: str | None


def is_configured() -> bool:
    return bool(settings.yookassa_shop_id and settings.yookassa_secret_key)


def _parse(data: dict) -> ProviderPayment:
    return ProviderPayment(
        id=data["id"],
        status=data["status"],
        paid=bool(data.get("paid")),
        amount=Decimal(data["amount"]["value"]),
        confirmation_url=(data.get("confirmation") or {}).get("confirmation_url"),
    )


async def _request(method: str, path: str, **kwargs) -> dict:
    auth = (settings.yookassa_shop_id, settings.yookassa_secret_key)
    try:
        async with httpx.AsyncClient(base_url=_API, auth=auth, timeout=20) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ConflictError("Платёжная система не ответила. Попробуйте ещё раз") from exc
    return response.json()


async def create_payment(
    amount: Decimal, description: str, return_url: str, idempotence_key: str, payment_ref: int
) -> ProviderPayment:
    data = await _request(
        "POST",
        "/payments",
        # Повторный запрос с тем же ключом вернёт тот же платёж, а не спишет деньги дважды
        headers={"Idempotence-Key": idempotence_key},
        json={
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description,
            "metadata": {"payment_ref": payment_ref},
        },
    )
    return _parse(data)


async def get_payment(provider_id: str) -> ProviderPayment:
    return _parse(await _request("GET", f"/payments/{provider_id}"))
