from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, ManagerMembership, Membership, SessionDep
from app.models import LedgerMember
from app.models.enums import MemberRole
from app.schemas.goal import (
    ContributionCreate,
    ContributionRead,
    GoalCreate,
    GoalMove,
    GoalRead,
    GoalUpdate,
)
from app.services import goal as goal_service

router = APIRouter(prefix="/ledgers/{ledger_id}/goals", tags=["goals"])


@router.get("")
async def list_goals(member: Membership, session: SessionDep) -> list[GoalRead]:
    return await goal_service.list_goals(session, member.ledger_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_goal(data: GoalCreate, member: ManagerMembership, session: SessionDep) -> GoalRead:
    return await goal_service.create_goal(session, member.ledger_id, data)


@router.patch("/{goal_id}")
async def update_goal(
    goal_id: int, data: GoalUpdate, member: ManagerMembership, session: SessionDep
) -> GoalRead:
    return await goal_service.update_goal(session, member.ledger_id, goal_id, data)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(goal_id: int, member: ManagerMembership, session: SessionDep) -> None:
    await goal_service.delete_goal(session, member.ledger_id, goal_id)


@router.post("/{goal_id}/move")
async def move_goal(
    goal_id: int, data: GoalMove, member: ManagerMembership, user: CurrentUser, session: SessionDep
) -> GoalRead:
    # Управлять нужно и целевым пространством: иначе можно подложить копилку в чужую семью
    target_role = await session.scalar(
        select(LedgerMember.role).where(
            LedgerMember.ledger_id == data.target_ledger_id, LedgerMember.user_id == user.id
        )
    )
    if target_role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пространство не найдено")
    return await goal_service.move_goal(session, member.ledger_id, goal_id, data)


@router.get("/{goal_id}/contributions")
async def list_contributions(
    goal_id: int, member: Membership, session: SessionDep
) -> list[ContributionRead]:
    return await goal_service.list_contributions(session, member.ledger_id, goal_id)


@router.post("/{goal_id}/contributions", status_code=status.HTTP_201_CREATED)
async def add_contribution(
    goal_id: int, data: ContributionCreate, member: Membership, session: SessionDep
) -> GoalRead:
    # Пополнять может любой участник: для того копилка и общая
    return await goal_service.add_contribution(
        session, member.ledger_id, goal_id, member.user_id, data
    )


@router.delete("/{goal_id}/contributions/{contribution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contribution(
    goal_id: int, contribution_id: int, member: ManagerMembership, session: SessionDep
) -> None:
    await goal_service.delete_contribution(session, member.ledger_id, goal_id, contribution_id)
