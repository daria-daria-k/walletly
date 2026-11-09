from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml import anomaly, categorizer, forecast
from app.ml.train import train_ledger
from app.models import MlModel, Subscription
from app.services import ml

pytestmark = pytest.mark.anyio

_TEXTS = {
    1: ["Пятёрочка у дома", "Перекрёсток продукты", "Магнит вечером", "ВкусВилл овощи", "Пятёрочка молоко"],
    2: ["Такси домой", "Метро проезд", "Яндекс такси", "Автобус утром", "Такси в аэропорт"],
    3: ["Кофе с собой", "Обед в кафе", "Ужин ресторан", "Кофейня латте", "Кафе завтрак"],
}


def _training_set() -> categorizer.TrainingSet:
    texts, labels = [], []
    for label, items in _TEXTS.items():
        for _ in range(4):
            texts += items
            labels += [label] * len(items)
    return categorizer.TrainingSet(texts, labels)


def test_prepare_rejects_too_little_data() -> None:
    assert categorizer.prepare(["a", "b"], [1, 2]) is None


def test_prepare_drops_rare_categories() -> None:
    data = categorizer.prepare(["кофе"] * 30 + ["чай"] * 2 + ["такси"] * 5, [1] * 30 + [2] * 2 + [3] * 5)
    assert data is not None and set(data.labels) == {1, 3}


@pytest.mark.parametrize("variant", ["A", "B"])
def test_models_learn_and_survive_serialization(variant: str) -> None:
    trained = categorizer.TRAINERS[variant](_training_set())
    assert trained.accuracy > 0.8
    predict = categorizer.load(variant, trained.payload)
    label, confidence = predict(["Такси домой"])[0]
    assert label == 2 and 0 <= confidence <= 1


def test_variant_is_stable_and_splits_users() -> None:
    assert ml.variant_for(7) == ml.variant_for(7)
    assert {ml.variant_for(user) for user in range(1, 50)} == {"A", "B"}


def test_p_value() -> None:
    assert ml.two_proportion_p_value(0, 0, 1, 1) is None
    assert ml.two_proportion_p_value(50, 100, 50, 100) == pytest.approx(1.0)
    assert ml.two_proportion_p_value(90, 100, 50, 100) < 0.001


def _steady_history(today: date, months: int = 6) -> list[tuple[date, float]]:
    rows = []
    day = today.replace(day=1)
    for _ in range(months * 31):
        day -= timedelta(days=1)
        rows.append((day, 1000.0))
    return rows


def test_forecast_needs_three_months() -> None:
    today = date(2026, 11, 15)
    assert forecast.predict([(date(2026, 10, 1), 100.0)], today) is None


def test_forecast_on_steady_spending_is_accurate() -> None:
    today = date(2026, 11, 15)
    current = [(date(2026, 11, day), 1000.0) for day in range(1, 16)]
    result = forecast.predict(_steady_history(today) + current, today)
    assert result is not None
    assert result.accuracy_percent >= 90
    assert 27_000 <= result.projected <= 33_000


def test_forecast_never_below_spent() -> None:
    today = date(2026, 11, 15)
    current = [(date(2026, 11, 2), 500_000.0)]
    result = forecast.predict(_steady_history(today) + current, today)
    assert result is not None and result.projected >= 500_000


def test_anomaly_finds_huge_purchase() -> None:
    rows = [anomaly.Row(n, 1, 500.0 + n % 7 * 10, n % 7, False) for n in range(1, 80)]
    rows.append(anomaly.Row(1000, 1, 25_000.0, 2, True))
    rows.append(anomaly.Row(1001, 1, 520.0, 3, True))
    found = anomaly.find(rows)
    assert found is not None and found.transaction_id == 1000


def test_anomaly_quiet_when_not_enough_data() -> None:
    assert anomaly.find([anomaly.Row(1, 1, 100.0, 1, True)]) is None


async def _premium(session: AsyncSession, user_id: int) -> None:
    session.add(Subscription(user_id=user_id, plan="premium"))
    await session.commit()


async def _fill(client: AsyncClient, user) -> tuple[int, dict[int, dict]]:
    base = f"/api/ledgers/{user.ledger_id}"
    account = (await client.post(f"{base}/accounts", json={"name": "Карта"}, headers=user.headers)).json()
    groups = (await client.get(f"{base}/category-groups", headers=user.headers)).json()
    expense = next(group for group in groups if group["type"] == "expense")["categories"][:3]
    mapping = {index + 1: category for index, category in enumerate(expense)}
    for label, items in _TEXTS.items():
        for _ in range(3):
            for text in items:
                response = await client.post(
                    f"{base}/transactions",
                    json={
                        "type": "expense",
                        "amount": "100",
                        "account_id": account["id"],
                        "category_id": mapping[label]["id"],
                        "description": text,
                        "tx_date": date.today().isoformat(),
                    },
                    headers=user.headers,
                )
                assert response.status_code == 201
    return account["id"], mapping


async def test_free_plan_cannot_use_suggestions(client: AsyncClient, register) -> None:
    user = await register()
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/ml/suggest-category",
        json={"description": "Такси"},
        headers=user.headers,
    )
    assert response.status_code == 403


async def test_train_suggest_and_record_outcome(
    client: AsyncClient, register, session: AsyncSession
) -> None:
    user = await register()
    await _premium(session, user.id)
    _, mapping = await _fill(client, user)

    results = await train_ledger(session, user.ledger_id)
    assert set(results) == {"A", "B"}
    assert len((await session.scalars(select(MlModel))).all()) == 2

    base = f"/api/ledgers/{user.ledger_id}/ml"
    response = await client.post(
        f"{base}/suggest-category", json={"description": "Такси домой"}, headers=user.headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category_id"] == mapping[2]["id"] and body["variant"] == ml.variant_for(user.id)

    outcome = await client.post(
        f"{base}/suggestions/{body['suggestion_id']}/outcome",
        json={"category_id": body["category_id"]},
        headers=user.headers,
    )
    assert outcome.status_code == 204
    report = await ml.ab_report(session)
    assert sum(item.accepted for item in report.variants) == 1


async def test_no_model_means_no_suggestion(
    client: AsyncClient, register, session: AsyncSession
) -> None:
    user = await register()
    await _premium(session, user.id)
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/ml/suggest-category",
        json={"description": "Такси"},
        headers=user.headers,
    )
    assert response.status_code == 200 and response.json() is None


async def test_outcome_of_another_user_is_rejected(
    client: AsyncClient, register, session: AsyncSession
) -> None:
    user = await register("a@example.com")
    stranger = await register("b@example.com")
    response = await client.post(
        f"/api/ledgers/{stranger.ledger_id}/ml/suggestions/999/outcome",
        json={"category_id": 1},
        headers=stranger.headers,
    )
    assert response.status_code == 403  # Free до проверки самой подсказки не доходит
    await _premium(session, stranger.id)
    response = await client.post(
        f"/api/ledgers/{stranger.ledger_id}/ml/suggestions/999/outcome",
        json={"category_id": 1},
        headers=stranger.headers,
    )
    assert response.status_code == 404
    assert user.id != stranger.id


async def test_import_fills_category_from_model(
    client: AsyncClient, register, session: AsyncSession
) -> None:
    user = await register()
    await _premium(session, user.id)
    _, mapping = await _fill(client, user)
    await train_ledger(session, user.ledger_id)

    csv = "Дата;Тип;Сумма;Счёт;Описание\n02.11.2026;расход;123;Карта;Такси домой\n"
    response = await client.post(
        f"/api/ledgers/{user.ledger_id}/import",
        files={"file": ("a.csv", csv.encode(), "text/csv")},
        headers=user.headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1
    rows = (
        await client.get(
            f"/api/ledgers/{user.ledger_id}/transactions",
            params={"search": "Такси домой", "date_to": "2026-11-02", "date_from": "2026-11-02"},
            headers=user.headers,
        )
    ).json()["items"]
    assert Decimal(rows[0]["amount"]) == 123 and rows[0]["category_id"] == mapping[2]["id"]
