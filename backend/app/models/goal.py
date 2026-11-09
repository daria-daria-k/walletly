from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IntPK
from app.models.finance import Account, Money


class SavingsGoal(Base):
    """Копилка. Личная она или общая, определяет пространство, которому она принадлежит."""

    __tablename__ = "savings_goals"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="target_positive"),
        CheckConstraint("monthly_contribution > 0", name="monthly_positive"),
        # До 28-го: это число есть в каждом месяце
        CheckConstraint("reminder_day BETWEEN 1 AND 28", name="reminder_day_range"),
    )

    id: Mapped[IntPK]
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), index=True)
    # RESTRICT: нельзя удалить счёт, на котором лежат деньги копилки
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    target_amount: Mapped[Decimal] = mapped_column(Money)
    monthly_contribution: Mapped[Decimal] = mapped_column(Money)
    reminder_day: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[CreatedAt]

    account: Mapped[Account] = relationship()
    contributions: Mapped[list["GoalContribution"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan", passive_deletes=True
    )


class GoalContribution(Base):
    """Пополнение. Накопленное считается суммой пополнений, а не остатком счёта:
    на одном накопительном счёте могут лежать деньги нескольких копилок."""

    __tablename__ = "goal_contributions"
    __table_args__ = (CheckConstraint("amount > 0", name="contribution_positive"),)

    id: Mapped[IntPK]
    goal_id: Mapped[int] = mapped_column(
        ForeignKey("savings_goals.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    contributed_on: Mapped[date]
    # Перевод, созданный вместе с пополнением. SET NULL: история копилки важнее операции
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    created_at: Mapped[CreatedAt]

    goal: Mapped[SavingsGoal] = relationship(back_populates="contributions")
