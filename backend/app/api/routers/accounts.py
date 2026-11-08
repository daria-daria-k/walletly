from fastapi import APIRouter, status

from app.api.deps import ManagerMembership, Membership, SessionDep
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate
from app.services import account as account_service

router = APIRouter(prefix="/ledgers/{ledger_id}/accounts", tags=["accounts"])


@router.get("")
async def list_accounts(
    member: Membership, session: SessionDep, include_archived: bool = False
) -> list[AccountRead]:
    return await account_service.list_accounts(session, member.ledger_id, include_archived)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_account(
    data: AccountCreate, member: ManagerMembership, session: SessionDep
) -> AccountRead:
    return await account_service.create_account(session, member.ledger_id, data)


@router.patch("/{account_id}")
async def update_account(
    account_id: int, data: AccountUpdate, member: ManagerMembership, session: SessionDep
) -> AccountRead:
    return await account_service.update_account(session, member.ledger_id, account_id, data)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, member: ManagerMembership, session: SessionDep) -> None:
    await account_service.delete_account(session, member.ledger_id, account_id)
