from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class Forecast(BaseModel):
    spent: Decimal
    projected: Decimal
    baseline: Decimal | None  # средние расходы за прошлые месяцы, если они есть
    change_percent: int | None
    month_progress: int  # сколько процентов месяца прошло
    method: str = "linear"  # linear — темп расходов, ml — обученная модель
    accuracy_percent: int | None = None  # только у модели: измерена на прошлых месяцах


class Anomaly(BaseModel):
    transaction_id: int
    title: str
    category_name: str
    amount: Decimal
    ratio: Decimal  # во сколько раз больше обычной операции этой категории
    tx_date: date


class Overspend(BaseModel):
    category_id: int
    category_name: str
    amount: Decimal  # сколько потрачено сверх обычного темпа


class LimitsStatus(BaseModel):
    total: int
    near: int
    over: int


class PlanItem(BaseModel):
    category_id: int
    category_name: str
    average: Decimal
    has_limit: bool


class Insights(BaseModel):
    forecast: Forecast
    anomaly: Anomaly | None
    overspend: Overspend | None
    limits: LimitsStatus
    plan: list[PlanItem]
    potential: Decimal
