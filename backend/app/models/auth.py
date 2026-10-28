from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, IntPK


class RefreshToken(Base):
    """Выданный refresh-токен. Сам токен не храним — только его SHA-256 хеш."""

    __tablename__ = "refresh_tokens"

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    # None — токен действует; дата — когда отозван (ротация, выход, подозрение на кражу)
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]
