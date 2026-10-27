from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPK
from app.models.enums import CategoryType


class CategoryGroup(Base):
    """Группа категорий: «Доходы», «Базовые», «Текущие», «Крупные» или своя."""

    __tablename__ = "category_groups"

    id: Mapped[IntPK]
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    # Тип наследуют все категории группы — у самой категории поля type нет
    type: Mapped[CategoryType]
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    categories: Mapped[list["Category"]] = relationship(back_populates="group")


class Category(Base):
    __tablename__ = "categories"
    # Индекс этого ограничения ускоряет и поиск по category_group_id — колонка в нём первая
    __table_args__ = (UniqueConstraint("category_group_id", "name"),)

    id: Mapped[IntPK]
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), index=True)
    # RESTRICT: группу с категориями удалить нельзя, сначала перенести категории
    category_group_id: Mapped[int] = mapped_column(
        ForeignKey("category_groups.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    group: Mapped[CategoryGroup] = relationship(back_populates="categories")
