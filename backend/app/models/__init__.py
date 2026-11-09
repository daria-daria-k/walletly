# Импорт всех моделей в одном месте: так они гарантированно регистрируются в Base.metadata.
# Alembic смотрит в metadata — модель, которую никто не импортировал, он не увидит
from app.models.auth import AdminAuditEntry, EmailToken, Notification, RefreshToken
from app.models.base import Base
from app.models.category import Category, CategoryGroup
from app.models.finance import Account, ImportBatch, Transaction
from app.models.goal import GoalContribution, SavingsGoal
from app.models.ledger import Invitation, Ledger, LedgerMember
from app.models.user import Subscription, User

__all__ = [
    "Account",
    "AdminAuditEntry",
    "Base",
    "Category",
    "CategoryGroup",
    "EmailToken",
    "GoalContribution",
    "ImportBatch",
    "Invitation",
    "Ledger",
    "LedgerMember",
    "Notification",
    "RefreshToken",
    "SavingsGoal",
    "Subscription",
    "Transaction",
    "User",
]
