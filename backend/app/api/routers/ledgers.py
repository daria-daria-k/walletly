from fastapi import APIRouter, status

from app.api.deps import CurrentUser, ManagerMembership, Membership, SessionDep
from app.models import LedgerMember
from app.models.enums import MemberRole
from app.schemas.ledger import LedgerCreate, LedgerRead, MemberRead, MemberRoleUpdate
from app.services import ledger as ledger_service
from app.services.errors import PermissionDeniedError

router = APIRouter(prefix="/ledgers", tags=["ledgers"])


def _ledger_read(member: LedgerMember) -> LedgerRead:
    ledger = member.ledger
    return LedgerRead(
        id=ledger.id,
        name=ledger.name,
        type=ledger.type,
        owner_id=ledger.owner_id,
        created_at=ledger.created_at,
        role=member.role,
    )


def _member_read(member: LedgerMember) -> MemberRead:
    return MemberRead(
        user_id=member.user_id,
        name=member.user.name,
        email=member.user.email,
        role=member.role,
        joined_at=member.joined_at,
    )


@router.get("")
async def list_ledgers(user: CurrentUser, session: SessionDep) -> list[LedgerRead]:
    return [_ledger_read(m) for m in await ledger_service.list_user_ledgers(session, user.id)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ledger(data: LedgerCreate, user: CurrentUser, session: SessionDep) -> LedgerRead:
    return _ledger_read(await ledger_service.create_shared_ledger(session, user, data.name))


@router.get("/{ledger_id}")
async def get_ledger(member: Membership) -> LedgerRead:
    return _ledger_read(member)


@router.patch("/{ledger_id}")
async def rename_ledger(
    data: LedgerCreate, member: ManagerMembership, session: SessionDep
) -> LedgerRead:
    await ledger_service.rename_ledger(session, member.ledger, data.name)
    return _ledger_read(member)


@router.delete("/{ledger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ledger(member: Membership, session: SessionDep) -> None:
    if member.role != MemberRole.OWNER:
        raise PermissionDeniedError("Удалить пространство может только владелец")
    await ledger_service.delete_ledger(session, member.ledger)


@router.get("/{ledger_id}/members")
async def list_members(member: Membership, session: SessionDep) -> list[MemberRead]:
    return [_member_read(m) for m in await ledger_service.list_members(session, member.ledger_id)]


@router.patch("/{ledger_id}/members/{user_id}")
async def change_member_role(
    user_id: int, data: MemberRoleUpdate, member: Membership, session: SessionDep
) -> MemberRead:
    return _member_read(
        await ledger_service.change_member_role(session, member, user_id, data.role)
    )


@router.delete("/{ledger_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(user_id: int, member: Membership, session: SessionDep) -> None:
    await ledger_service.remove_member(session, member, user_id)
