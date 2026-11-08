from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import Membership, SessionDep
from app.models.enums import TransactionType
from app.schemas.transaction import AnalyticsSummary, AuthorTotal, CategoryTotal, MonthTotal
from app.services import analytics as analytics_service

router = APIRouter(prefix="/ledgers/{ledger_id}/analytics", tags=["analytics"])

Currency = Annotated[str, Query(pattern=r"^[A-Z]{3}$")]


@router.get("/summary")
async def summary(
    member: Membership,
    session: SessionDep,
    currency: Currency = "RUB",
    date_from: date | None = None,
    date_to: date | None = None,
) -> AnalyticsSummary:
    return await analytics_service.summary(session, member.ledger_id, currency, date_from, date_to)


@router.get("/by-category")
async def by_category(
    member: Membership,
    session: SessionDep,
    type: TransactionType = TransactionType.EXPENSE,
    currency: Currency = "RUB",
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[CategoryTotal]:
    return await analytics_service.by_category(
        session, member.ledger_id, type, currency, date_from, date_to
    )


@router.get("/by-author")
async def by_author(
    member: Membership,
    session: SessionDep,
    currency: Currency = "RUB",
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[AuthorTotal]:
    return await analytics_service.by_author(
        session, member.ledger_id, currency, date_from, date_to
    )


@router.get("/monthly")
async def monthly(
    member: Membership,
    session: SessionDep,
    currency: Currency = "RUB",
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[MonthTotal]:
    return await analytics_service.monthly(session, member.ledger_id, currency, date_from, date_to)
