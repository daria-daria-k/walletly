from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import AccountKind
from app.schemas.common import CurrencyCode, Money, Name50


class AccountCreate(BaseModel):
    name: Name50
    currency: CurrencyCode = "RUB"
    kind: AccountKind = AccountKind.CARD
    initial_balance: Money = Decimal(0)
    sort_order: int = 0


class AccountUpdate(BaseModel):
    # default=None при типе без None: поле можно не передавать, но явный null — ошибка 422.
    # Иначе null дошёл бы до NOT NULL колонки и превратился в 500.
    # Валюты здесь нет намеренно: смена валюты исказила бы все прошлые операции
    name: Name50 = Field(default=None)
    kind: AccountKind = Field(default=None)
    initial_balance: Money = Field(default=None)
    is_active: bool = Field(default=None)
    sort_order: int = Field(default=None)


class AccountRead(BaseModel):
    id: int
    name: str
    currency: str
    kind: AccountKind
    initial_balance: Decimal
    balance: Decimal
    month_change: Decimal  # изменение остатка с начала текущего месяца
    is_active: bool
    sort_order: int
