"""Прогноз расходов на конец месяца с измеренной на истории точностью."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

import numpy as np
from sklearn.linear_model import Ridge

MIN_MONTHS = 3
_MAX_MONTHS = 24
_FIRST_DAY_LIMIT = 5


@dataclass(frozen=True)
class MlForecast:
    projected: float
    accuracy_percent: int
    months_used: int


def _key(day: date) -> tuple[int, int]:
    return day.year, day.month


def _features(day: int, days: int, spent: float, previous: float) -> list[float]:
    progress = day / days
    # Линейная оценка входит как признак: модель учится её поправлять, а не заменять
    return [progress, spent, previous, spent / progress]


def _samples(
    months: list[tuple[int, int]], daily: dict[tuple[int, int], dict[int, float]], totals: dict
) -> tuple[list[list[float]], list[float]]:
    x: list[list[float]] = []
    y: list[float] = []
    for position, month in enumerate(months):
        days = monthrange(*month)[1]
        previous = totals[months[position - 1]] if position else totals[month]
        spent = 0.0
        for day in range(1, days + 1):
            spent += daily[month].get(day, 0.0)
            x.append(_features(day, days, spent, previous))
            y.append(totals[month])
    return x, y


def _fit(x: list[list[float]], y: list[float], scale: float) -> Ridge:
    # Нормируем на средний месяц: иначе штраф Ridge зависел бы от размера дохода семьи
    return Ridge(alpha=1.0).fit(np.array(x) / scale, np.array(y) / scale)


def predict(expenses: list[tuple[date, float]], today: date) -> MlForecast | None:
    """None — истории меньше трёх полных месяцев: честно оценить точность ещё нельзя."""
    daily: dict[tuple[int, int], dict[int, float]] = {}
    for day, amount in expenses:
        month = daily.setdefault(_key(day), {})
        month[day.day] = month.get(day.day, 0.0) + amount

    current = _key(today)
    months = sorted(month for month in daily if month < current)[-_MAX_MONTHS:]
    # Месяц, с середины которого начали вести учёт, неполный: его сумма исказила бы обучение
    if months and min(daily[months[0]]) > _FIRST_DAY_LIMIT:
        months = months[1:]
    if len(months) < MIN_MONTHS:
        return None
    totals = {month: sum(daily[month].values()) for month in months}
    scale = float(np.mean(list(totals.values())))
    if scale <= 0:
        return None

    # Проверка без подглядывания: каждый месяц предсказываем моделью, не видевшей его
    errors: list[float] = []
    for held_out in months:
        rest = [month for month in months if month != held_out]
        x, y = _samples(rest, daily, totals)
        model = _fit(x, y, scale)
        days = monthrange(*held_out)[1]
        day = min(today.day, days)
        spent = sum(value for key, value in daily[held_out].items() if key <= day)
        position = months.index(held_out)
        previous = totals[months[position - 1]] if position else scale
        guess = float(model.predict(np.array([_features(day, days, spent, previous)]) / scale)[0]) * scale
        if totals[held_out] > 0:
            errors.append(abs(guess - totals[held_out]) / totals[held_out])

    x, y = _samples(months, daily, totals)
    model = _fit(x, y, scale)
    days = monthrange(*current)[1]
    spent = sum(value for key, value in daily.get(current, {}).items() if key <= today.day)
    value = float(
        model.predict(np.array([_features(today.day, days, spent, totals[months[-1]])]) / scale)[0]
    )
    # Прогноз не может быть меньше уже потраченного
    projected = max(value * scale, spent)
    accuracy = max(0, round((1 - float(np.mean(errors))) * 100)) if errors else 0
    return MlForecast(round(projected, 2), accuracy, len(months))
