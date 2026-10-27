from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IntPK
from app.models.category import Category
from app.models.enums import TransactionType

# Деньги: 12 цифр, 2 после запятой. В Python — Decimal, не float
Money = Numeric(12, 2)


class Account(Base):
    """Счёт: банковская карта, вклад, наличные. Текущий остаток не хранится — вычисляется."""

    __tablename__ = "accounts"

    id: Mapped[IntPK]
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(3), default="RUB", server_default="RUB")
    # Остаток на момент начала учёта в Walletly
    initial_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal(0), server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        # Какие поля обязательны, зависит от типа операции
        CheckConstraint(
            "(type = 'transfer' AND to_account_id IS NOT NULL AND category_id IS NULL"
            " AND to_account_id <> account_id)"
            " OR (type IN ('income', 'expense') AND category_id IS NOT NULL"
            " AND to_account_id IS NULL)",
            name="fields_match_type",
        ),
        # История и аналитика всегда фильтруют по ledger и периоду
        Index("ix_transactions_ledger_id_tx_date", "ledger_id", "tx_date"),
    )

    id: Mapped[IntPK]
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"))
    # Автор записи. RESTRICT: история семьи не должна исчезать вместе с пользователем
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    type: Mapped[TransactionType]
    amount: Mapped[Decimal] = mapped_column(Money)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    to_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    description: Mapped[str | None] = mapped_column(String(500))
    tx_date: Mapped[date]
    is_deleted: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[CreatedAt]

    # Два внешних ключа на accounts — нужно явно сказать, какой связи какой ключ
    account: Mapped[Account] = relationship(foreign_keys=[account_id])
    to_account: Mapped[Account | None] = relationship(foreign_keys=[to_account_id])
    category: Mapped[Category | None] = relationship()
