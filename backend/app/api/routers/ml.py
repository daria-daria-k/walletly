from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import Membership, SessionDep
from app.services import billing, ml

router = APIRouter(prefix="/ledgers/{ledger_id}/ml", tags=["ml"])


class SuggestRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)


class SuggestResponse(BaseModel):
    suggestion_id: int
    category_id: int
    confidence: float
    variant: str


class OutcomeRequest(BaseModel):
    category_id: int


@router.post("/suggest-category")
async def suggest_category(
    data: SuggestRequest, member: Membership, session: SessionDep
) -> SuggestResponse | None:
    await billing.require_premium(session, member.user_id, "Умная категоризация")
    found = await ml.suggest_category(session, member.ledger_id, member.user_id, data.description)
    if found is None:
        return None
    return SuggestResponse(
        suggestion_id=found.suggestion_id,
        category_id=found.category_id,
        confidence=found.confidence,
        variant=ml.variant_for(member.user_id),
    )


@router.post("/suggestions/{suggestion_id}/outcome", status_code=status.HTTP_204_NO_CONTENT)
async def record_outcome(
    suggestion_id: int, data: OutcomeRequest, member: Membership, session: SessionDep
) -> None:
    await billing.require_premium(session, member.user_id, "Умная категоризация")
    await ml.record_outcome(
        session, member.ledger_id, member.user_id, suggestion_id, data.category_id
    )
