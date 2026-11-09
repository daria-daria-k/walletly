from enum import StrEnum


class UserRole(StrEnum):
    """Роль в системе."""

    USER = "user"
    ADMIN = "admin"


class Plan(StrEnum):
    FREE = "free"
    PREMIUM = "premium"


class LedgerType(StrEnum):
    PERSONAL = "personal"
    SHARED = "shared"


class MemberRole(StrEnum):
    """Роль внутри пространства (ledger)."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class CategoryType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class AccountKind(StrEnum):
    CARD = "card"
    SAVINGS = "savings"
    DEPOSIT = "deposit"
    CASH = "cash"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"


class EmailTokenPurpose(StrEnum):
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
