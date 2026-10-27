from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IntPK
from app.models.enums import InvitationStatus, LedgerType, MemberRole

if TYPE_CHECKING:
    from app.models.user import User


class Ledger(Base):
    """Пространство учёта: личное (у каждого пользователя одно) или общее (семья)."""

    __tablename__ = "ledgers"
    __table_args__ = (
        # Частичный уникальный индекс: уникальность owner_id только среди личных ledger.
        # Общих пространств у одного владельца может быть сколько угодно
        Index(
            "uq_ledgers_personal_owner_id",
            "owner_id",
            unique=True,
            postgresql_where=text("type = 'personal'"),
        ),
    )

    id: Mapped[IntPK]
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[LedgerType]
    # RESTRICT: нельзя удалить пользователя, пока он владеет пространством
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[CreatedAt]

    owner: Mapped["User"] = relationship()
    members: Mapped[list["LedgerMember"]] = relationship(back_populates="ledger")
    invitations: Mapped[list["Invitation"]] = relationship(back_populates="ledger")


class LedgerMember(Base):
    """Связующая таблица users ↔ ledgers (многие-ко-многим) с ролью участника."""

    __tablename__ = "ledger_members"
    __table_args__ = (UniqueConstraint("ledger_id", "user_id"),)

    id: Mapped[IntPK]
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"))
    # Отдельный индекс: частый запрос «в каких ledger состоит пользователь».
    # Уникальный индекс (ledger_id, user_id) тут не помогает — user_id в нём второй
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[MemberRole] = mapped_column(
        default=MemberRole.MEMBER, server_default=MemberRole.MEMBER.value
    )
    joined_at: Mapped[CreatedAt]

    ledger: Mapped[Ledger] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[IntPK]
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    invited_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Случайная строка для ссылки-приглашения
    token: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[InvitationStatus] = mapped_column(
        default=InvitationStatus.PENDING, server_default=InvitationStatus.PENDING.value
    )
    expires_at: Mapped[datetime]
    created_at: Mapped[CreatedAt]

    ledger: Mapped[Ledger] = relationship(back_populates="invitations")
