import enum
from datetime import datetime
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, Enum, Identity, MetaData, func
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Шаблоны имён для ограничений и индексов. Без них PostgreSQL придумает имена сам,
# и Alembic не сможет надёжно найти ограничение, чтобы изменить или удалить его
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    """Родитель всех моделей: общий реестр таблиц (metadata) и правила типов."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Какой SQL-тип ставить по Python-аннотации, если тип не указан явно
    type_annotation_map = {
        int: BigInteger,
        datetime: DateTime(timezone=True),
        # В БД храним значение enum ("user"), а не имя члена Python ("USER")
        enum.Enum: Enum(enum.Enum, values_callable=lambda e: [m.value for m in e]),
    }


# Переиспользуемые типы колонок
IntPK = Annotated[int, mapped_column(Identity(always=True), primary_key=True)]
CreatedAt = Annotated[datetime, mapped_column(server_default=func.now())]
