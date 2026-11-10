"""category icons

Revision ID: a6c971edbf42
Revises: e9315b6a2833
Create Date: 2026-11-10 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6c971edbf42"
down_revision: Union[str, Sequence[str], None] = "e9315b6a2833"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("icon_key", sa.String(length=50), nullable=True))
    # Существующим базовым категориям назначаем те же ключи, что получат новые пространства.
    mapping = {
        "Зарплата": "Зарплата", "Подработка": "Подработка",
        "Кешбэк и проценты": "Кешбэк и проценты", "Подарки": "Подарки",
        "Прочие доходы": "Прочие доходы", "Продукты": "Продукты",
        "Жильё и ЖКХ": "Жильё и аренда", "Транспорт": "Транспорт",
        "Связь и интернет": "Связь и интернет", "Здоровье": "Здоровье и лекарства",
        "Кафе и рестораны": "Кафе и рестораны", "Развлечения": "Развлечения",
        "Одежда и обувь": "Одежда и обувь", "Красота": "Красота и уход",
        "Подписки": "Подписки и сервисы", "Техника": "Электроника",
        "Ремонт и мебель": "Ремонт", "Путешествия": "Путешествия",
        "Обучение": "Образование",
    }
    categories = sa.table("categories", sa.column("name", sa.String), sa.column("icon_key", sa.String))
    for name, icon_key in mapping.items():
        op.execute(categories.update().where(categories.c.name == name).values(icon_key=icon_key))


def downgrade() -> None:
    op.drop_column("categories", "icon_key")
