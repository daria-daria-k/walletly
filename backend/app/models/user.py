from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Numeric, String, false, text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IntPK
from app.models.enums import PaymentStatus, Plan, UserRole

if TYPE_CHECKING:
    from app.models.ledger import LedgerMember


class User(Base):
    __tablename__ = "users"

    id: Mapped[IntPK]
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(default=UserRole.USER, server_default=UserRole.USER.value)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Новый пользователь проходит первичную настройку, существующих миграция отмечает готовыми
    onboarding_completed: Mapped[bool] = mapped_column(default=False, server_default=false())
    # JSON, а не колонки: набор событий будет меняться, пустой объект означает значения по умолчанию
    notifications: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    # None — адрес не подтверждён. Вход не запрещаем: письмо может задержаться
    email_verified_at: Mapped[datetime | None]
    # BigInteger: номера чатов Telegram не помещаются в обычный int
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    created_at: Mapped[CreatedAt]

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    memberships: Mapped[list["LedgerMember"]] = relationship(back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[Plan]
    starts_at: Mapped[CreatedAt]
    # None — бессрочно
    expires_at: Mapped[datetime | None]

    user: Mapped[User] = relationship(back_populates="subscriptions")


class Payment(Base):
    """Попытка оплаты подписки. Запись создаётся до обращения к платёжной системе."""

    __tablename__ = "payments"

    id: Mapped[IntPK]
    # RESTRICT: платёжные записи нужно хранить, даже если пользователь уходит
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[PaymentStatus] = mapped_column(
        default=PaymentStatus.PENDING, server_default=PaymentStatus.PENDING.value
    )
    # None, пока ЮKassa не ответила на создание платежа
    provider_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    idempotence_key: Mapped[str] = mapped_column(String(64), unique=True)
    paid_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]
