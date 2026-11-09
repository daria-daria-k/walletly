from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import Name50

# Строго больше нуля и в пределах колонки NUMERIC(12,2)
PositiveMoney = Field(gt=0, max_digits=12, decimal_places=2)


class GoalCreate(BaseModel):
    name: Name50
    target_amount: Decimal = PositiveMoney
    monthly_contribution: Decimal = PositiveMoney
    account_id: int
    reminder_day: int = Field(default=1, ge=1, le=28)


class GoalUpdate(BaseModel):
    name: Name50 = Field(default=None)
    target_amount: Decimal = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    monthly_contribution: Decimal = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    account_id: int = Field(default=None)
    reminder_day: int = Field(default=None, ge=1, le=28)


class GoalMove(BaseModel):
    target_ledger_id: int
    account_id: int


class ContributionCreate(BaseModel):
    amount: Decimal = PositiveMoney
    contributed_on: date | None = None
    # Счёт, с которого переводим. Без него деньги считаются уже лежащими в копилке
    from_account_id: int | None = None


class ContributionRead(BaseModel):
    id: int
    user_name: str
    amount: Decimal
    contributed_on: date
    from_transfer: bool
    created_at: datetime


class GoalRead(BaseModel):
    id: int
    ledger_id: int
    name: str
    target_amount: Decimal
    monthly_contribution: Decimal
    account_id: int
    account_name: str
    currency: str
    reminder_day: int
    saved: Decimal
    remaining: Decimal
    progress_percent: int
    months_left: int
    # Первое число месяца, к которому цель будет достигнута; None — уже достигнута
    forecast_month: date | None
    contributed_this_month: bool
    missed_last_month: bool
    reminder_due: bool
