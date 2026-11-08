from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import TransactionType
from app.schemas.common import PositiveMoney

Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class TransactionCreate(BaseModel):
    type: TransactionType
    amount: PositiveMoney
    account_id: int
    to_account_id: int | None = None
    category_id: int | None = None
    description: Description | None = None
    tx_date: date


class TransactionUpdate(BaseModel):
    type: TransactionType = Field(default=None)
    amount: PositiveMoney = Field(default=None)
    account_id: int = Field(default=None)
    # Эти поля могут быть null по смыслу: у перевода нет категории, у расхода — счёта «куда»
    to_account_id: int | None = None
    category_id: int | None = None
    description: Description | None = None
    tx_date: date = Field(default=None)


class TransactionRead(BaseModel):
    id: int
    ledger_id: int
    user_id: int
    author_name: str
    type: TransactionType
    amount: Decimal
    account_id: int
    to_account_id: int | None
    category_id: int | None
    description: str | None
    tx_date: date
    created_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionRead]
    total: int
    limit: int
    offset: int


class AnalyticsSummary(BaseModel):
    income: Decimal
    expense: Decimal
    net: Decimal


class CategoryTotal(BaseModel):
    category_id: int
    category_name: str
    group_name: str
    total: Decimal


class MonthTotal(BaseModel):
    month: str  # YYYY-MM
    income: Decimal
    expense: Decimal
