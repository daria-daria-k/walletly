from fastapi import APIRouter, status

from app.api.deps import CurrentUser, ManagerMembership, SessionDep
from app.schemas.invitation import InvitationCreate, InvitationPreview, InvitationRead
from app.services import invitation as invitation_service

router = APIRouter(tags=["invitations"])


@router.get("/ledgers/{ledger_id}/invitations")
async def list_invitations(member: ManagerMembership, session: SessionDep) -> list[InvitationRead]:
    invitations = await invitation_service.list_invitations(session, member.ledger_id)
    return [InvitationRead.model_validate(i) for i in invitations]


@router.post("/ledgers/{ledger_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    data: InvitationCreate, member: ManagerMembership, session: SessionDep
) -> InvitationRead:
    invitation = await invitation_service.create_invitation(session, member, data.email)
    return InvitationRead.model_validate(invitation)


@router.delete(
    "/ledgers/{ledger_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_invitation(
    invitation_id: int, member: ManagerMembership, session: SessionDep
) -> None:
    await invitation_service.revoke_invitation(session, member.ledger_id, invitation_id)


@router.get("/invitations/{token}")
async def preview_invitation(
    token: str, user: CurrentUser, session: SessionDep
) -> InvitationPreview:
    invitation, ledger = await invitation_service.get_by_token(session, token)
    return InvitationPreview(
        ledger_name=ledger.name,
        invited_email=invitation.email,
        status=invitation.status,
        expires_at=invitation.expires_at,
    )


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str, user: CurrentUser, session: SessionDep
) -> dict[str, int]:
    return {"ledger_id": await invitation_service.accept_invitation(session, token, user)}


@router.post("/invitations/{token}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_invitation(token: str, user: CurrentUser, session: SessionDep) -> None:
    await invitation_service.decline_invitation(session, token, user)
