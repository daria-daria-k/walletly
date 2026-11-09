from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Payment, Subscription, User
from app.models.enums import PaymentStatus, Plan
from app.services import yookassa
from app.services.auth import current_subscription
from app.services.errors import ConflictError, NotFoundError, PermissionDeniedError

PERIOD = timedelta(days=30)


def premium_price() -> Decimal:
    return Decimal(settings.premium_price_rub)


async def get_plan(session: AsyncSession, user_id: int) -> Plan:
    return (await current_subscription(session, user_id)).plan


async def require_premium(session: AsyncSession, user_id: int, feature: str) -> None:
    if await get_plan(session, user_id) != Plan.PREMIUM:
        raise PermissionDeniedError(f"{feature} доступно в тарифе Premium")


async def start_checkout(session: AsyncSession, user: User) -> str:
    """Создаёт платёж и возвращает страницу оплаты."""
    if not yookassa.is_configured():
        raise ConflictError("Оплата пока не настроена")

    amount = premium_price()
    # Сначала строка у нас, потом запрос к ЮKassa: номер платежа должен существовать заранее,
    # а ключ идемпотентности защищает от двойного платежа при повторе
    payment = Payment(user_id=user.id, amount=amount, idempotence_key=uuid4().hex)
    session.add(payment)
    await session.commit()

    remote = await yookassa.create_payment(
        amount,
        "Walletly Premium, 30 дней",
        f"{settings.app_url}/settings?payment={payment.id}",
        payment.idempotence_key,
        payment.id,
    )
    payment.provider_id = remote.id
    await session.commit()
    if remote.confirmation_url is None:
        raise ConflictError("Платёжная система не вернула страницу оплаты")
    return remote.confirmation_url


async def _apply_remote_status(session: AsyncSession, payment: Payment) -> Payment:
    """Статус всегда берём из API ЮKassa, а не из тела входящего запроса:
    так поддельное уведомление не сможет выдать Premium."""
    remote = await yookassa.get_payment(payment.provider_id)
    if remote.status == "canceled":
        payment.status = PaymentStatus.CANCELED
    elif remote.status == "succeeded" and remote.paid and remote.amount == payment.amount:
        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = datetime.now(UTC)
        await _extend_premium(session, payment.user_id)
    await session.commit()
    return payment


async def _extend_premium(session: AsyncSession, user_id: int) -> None:
    now = datetime.now(UTC)
    current = await current_subscription(session, user_id)
    # Оплата до окончания добавляет дни к сроку, а не сгорает
    start = current.expires_at if current.plan == Plan.PREMIUM and current.expires_at else now
    session.add(Subscription(user_id=user_id, plan=Plan.PREMIUM, expires_at=start + PERIOD))


async def _locked_pending(session: AsyncSession, query) -> Payment | None:
    # Блокировка строки: уведомление и возврат пользователя могут прийти одновременно,
    # а продлить подписку нужно только один раз
    return await session.scalar(query.with_for_update())


async def sync_payment(session: AsyncSession, user_id: int, payment_id: int) -> Payment:
    payment = await _locked_pending(
        session, select(Payment).where(Payment.id == payment_id, Payment.user_id == user_id)
    )
    if payment is None:
        raise NotFoundError("Платёж не найден")
    if payment.status == PaymentStatus.PENDING and payment.provider_id:
        await _apply_remote_status(session, payment)
    return payment


async def handle_webhook(session: AsyncSession, provider_id: str) -> None:
    payment = await _locked_pending(
        session, select(Payment).where(Payment.provider_id == provider_id)
    )
    if payment is not None and payment.status == PaymentStatus.PENDING:
        await _apply_remote_status(session, payment)


async def list_payments(session: AsyncSession, user_id: int) -> list[Payment]:
    items = await session.scalars(
        select(Payment).where(Payment.user_id == user_id).order_by(Payment.id.desc()).limit(50)
    )
    return list(items)
