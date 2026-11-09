from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, false, text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IntPK
from app.models.enums import Plan, UserRole

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
