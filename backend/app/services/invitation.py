import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Invitation, Ledger, LedgerMember, User
from app.models.enums import InvitationStatus, LedgerType, MemberRole
from app.services.errors import ConflictError, NotFoundError, PermissionDeniedError

INVITATION_TTL = timedelta(days=7)


async def create_invitation(session: AsyncSession, actor: LedgerMember, email: str) -> Invitation:
    if actor.ledger.type == LedgerType.PERSONAL:
        raise ConflictError("В личное пространство нельзя приглашать")

    already_member = await session.scalar(
        select(LedgerMember.id)
        .join(User, LedgerMember.user_id == User.id)
        .where(LedgerMember.ledger_id == actor.ledger_id, User.email == email)
    )
    if already_member:
        raise ConflictError("Этот пользователь уже в пространстве")

    now = datetime.now(UTC)
    pending = await session.scalar(
        select(Invitation.id).where(
            Invitation.ledger_id == actor.ledger_id,
            Invitation.email == email,
            Invitation.status == InvitationStatus.PENDING,
            Invitation.expires_at > now,
        )
    )
    if pending:
        raise ConflictError("Приглашение на этот email уже отправлено")

    invitation = Invitation(
        ledger_id=actor.ledger_id,
        email=email,
        invited_by=actor.user_id,
        token=secrets.token_urlsafe(32),  # ссылку нельзя угадать перебором
        expires_at=now + INVITATION_TTL,
    )
    session.add(invitation)
    await session.commit()
    return invitation


async def list_invitations(session: AsyncSession, ledger_id: int) -> list[Invitation]:
    result = await session.scalars(
        select(Invitation)
        .where(Invitation.ledger_id == ledger_id)
        .order_by(Invitation.created_at.desc(), Invitation.id.desc())
    )
    return list(result)


async def revoke_invitation(session: AsyncSession, ledger_id: int, invitation_id: int) -> None:
    invitation = await session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.ledger_id == ledger_id
        )
    )
    if invitation is None:
        raise NotFoundError("Приглашение не найдено")
    if invitation.status != InvitationStatus.PENDING:
        raise ConflictError("Приглашение уже обработано")
    await session.delete(invitation)
    await session.commit()


async def get_by_token(session: AsyncSession, token: str) -> tuple[Invitation, Ledger]:
    invitation = await session.scalar(
        select(Invitation).options(joinedload(Invitation.ledger)).where(Invitation.token == token)
    )
    if invitation is None:
        raise NotFoundError("Приглашение не найдено")
    return invitation, invitation.ledger


async def _lock_pending(session: AsyncSession, token: str, user: User) -> Invitation:
    invitation = await session.scalar(
        select(Invitation)
        .where(Invitation.token == token)
        # Блокировка: двойной клик по «Принять» выполнится по очереди,
        # и второй запрос увидит, что приглашение уже обработано
        .with_for_update()
    )
    if invitation is None:
        raise NotFoundError("Приглашение не найдено")
    if invitation.email != user.email:
        raise PermissionDeniedError("Приглашение отправлено на другой email")
    if invitation.status != InvitationStatus.PENDING:
        raise ConflictError("Приглашение уже обработано")
    if invitation.expires_at <= datetime.now(UTC):
        invitation.status = InvitationStatus.EXPIRED
        await session.commit()
        raise ConflictError("Срок приглашения истёк")
    return invitation


async def accept_invitation(session: AsyncSession, token: str, user: User) -> int:
    invitation = await _lock_pending(session, token, user)
    existing = await session.scalar(
        select(LedgerMember.id).where(
            LedgerMember.ledger_id == invitation.ledger_id, LedgerMember.user_id == user.id
        )
    )
    if existing is None:
        session.add(
            LedgerMember(ledger_id=invitation.ledger_id, user_id=user.id, role=MemberRole.MEMBER)
        )
    invitation.status = InvitationStatus.ACCEPTED
    await session.commit()
    return invitation.ledger_id


async def decline_invitation(session: AsyncSession, token: str, user: User) -> None:
    invitation = await _lock_pending(session, token, user)
    invitation.status = InvitationStatus.DECLINED
    await session.commit()
