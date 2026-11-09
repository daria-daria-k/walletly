"""Поиск необычных трат с помощью Isolation Forest."""

import math
from dataclasses import dataclass
from statistics import mean, median, pstdev

import numpy as np
from sklearn.ensemble import IsolationForest

MIN_ROWS = 40
_MIN_RATIO = 1.5  # выброс по форме, но близкий к обычной сумме, тревоги не стоит


@dataclass(frozen=True)
class Row:
    transaction_id: int
    category_id: int
    amount: float
    weekday: int
    is_current: bool


@dataclass(frozen=True)
class Found:
    transaction_id: int
    ratio: float


def find(rows: list[Row]) -> Found | None:
    if len(rows) < MIN_ROWS or not any(row.is_current for row in rows):
        return None

    by_category: dict[int, list[float]] = {}
    for row in rows:
        by_category.setdefault(row.category_id, []).append(row.amount)

    # Сумма сравнивается и с общими тратами, и со своей категорией:
    # 5000 ₽ нормально для квартплаты и странно для кофе
    features = []
    for row in rows:
        values = by_category[row.category_id]
        spread = pstdev(values) or 1.0
        features.append(
            [
                math.log1p(row.amount),
                (row.amount - mean(values)) / spread,
                math.sin(2 * math.pi * row.weekday / 7),
            ]
        )

    matrix = np.array(features)
    model = IsolationForest(n_estimators=100, contamination="auto", random_state=42).fit(matrix)
    flags = model.predict(matrix)
    scores = model.score_samples(matrix)

    best: Found | None = None
    best_score = 0.0
    for row, flag, score in zip(rows, flags, scores, strict=True):
        usual = median(by_category[row.category_id])
        ratio = row.amount / usual if usual else 0.0
        if row.is_current and flag == -1 and ratio >= _MIN_RATIO and (best is None or score < best_score):
            best = Found(row.transaction_id, round(ratio, 1))
            best_score = float(score)
    return best
