from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import Membership, SessionDep
from app.models.enums import TransactionType
from app.schemas.transaction import (
    TransactionCreate,
    TransactionPage,
    TransactionRead,
    TransactionUpdate,
)
from app.services import transaction as transaction_service
from app.services.transaction import TransactionFilters

router = APIRouter(prefix="/ledgers/{ledger_id}/transactions", tags=["transactions"])


def _filters(
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    type: TransactionType | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> TransactionFilters:
    return TransactionFilters(date_from, date_to, account_id, category_id, type, search)


@router.get("")
async def list_transactions(
    member: Membership,
    session: SessionDep,
    filters: Annotated[TransactionFilters, Depends(_filters)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    items, total = await transaction_service.list_transactions(
        session, member.ledger_id, filters, limit, offset
    )
    return TransactionPage(
        items=[transaction_service.to_read(tx) for tx in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate, member: Membership, session: SessionDep
) -> TransactionRead:
    tx = await transaction_service.create_transaction(session, member, data)
    return transaction_service.to_read(tx)


@router.get("/{tx_id}")
async def get_transaction(tx_id: int, member: Membership, session: SessionDep) -> TransactionRead:
    tx = await transaction_service.get_transaction(session, member.ledger_id, tx_id)
    return transaction_service.to_read(tx)


@router.patch("/{tx_id}")
async def update_transaction(
    tx_id: int, data: TransactionUpdate, member: Membership, session: SessionDep
) -> TransactionRead:
    tx = await transaction_service.update_transaction(session, member, tx_id, data)
    return transaction_service.to_read(tx)


@router.delete("/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(tx_id: int, member: Membership, session: SessionDep) -> None:
    await transaction_service.delete_transaction(session, member, tx_id)
