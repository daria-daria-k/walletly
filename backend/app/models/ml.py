from sqlalchemy import Float, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, IntPK


class MlModel(Base):
    """Обученная модель пространства. В БД, а не в файле: её читают и API, и worker,
    а модели здесь маленькие и попадают в обычный бэкап."""

    __tablename__ = "ml_models"
    __table_args__ = (UniqueConstraint("ledger_id", "task", "variant", name="uq_ml_model"),)

    id: Mapped[IntPK]
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), index=True)
    task: Mapped[str] = mapped_column(String(30))
    variant: Mapped[str] = mapped_column(String(1))
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    accuracy: Mapped[float] = mapped_column(Float)
    samples: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[CreatedAt]


class MlSuggestion(Base):
    """Показанная подсказка: по ней сравниваются варианты A/B. Текст описания не хранится."""

    __tablename__ = "ml_suggestions"

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), index=True)
    variant: Mapped[str] = mapped_column(String(1), index=True)
    # Без внешнего ключа: запись должна пережить удаление категории
    suggested_category_id: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float)
    # None — пользователь ещё не сохранил операцию или закрыл форму
    accepted: Mapped[bool | None]
    created_at: Mapped[CreatedAt]
