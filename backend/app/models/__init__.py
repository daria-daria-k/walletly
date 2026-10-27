# Импорт всех моделей в одном месте: так они гарантированно регистрируются в Base.metadata.
# Alembic смотрит в metadata — модель, которую никто не импортировал, он не увидит
from app.models.base import Base
from app.models.ledger import Invitation, Ledger, LedgerMember
from app.models.user import Subscription, User

__all__ = ["Base", "Invitation", "Ledger", "LedgerMember", "Subscription", "User"]
