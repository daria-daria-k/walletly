from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.database import get_session
from app.core.security import decode_access_token
from app.models import LedgerMember, User
from app.models.enums import MemberRole, UserRole

# Короткий псевдоним: в эндпоинте пишем `session: SessionDep` вместо полной записи Depends
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# auto_error=False: без заголовка вернём наш 401, а не стандартный 403 от FastAPI
_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Требуется вход", headers={"WWW-Authenticate": "Bearer"}
    )


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise _unauthorized()
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise _unauthorized() from None

    # Идём в БД, хотя JWT уже подтвердил личность: блокировка должна работать сразу,
    # а не когда истечёт access-токен (до 15 минут)
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_admin_user(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужны права администратора")
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


async def get_membership(ledger_id: int, user: CurrentUser, session: SessionDep) -> LedgerMember:
    member = await session.scalar(
        select(LedgerMember)
        .options(joinedload(LedgerMember.ledger))
        .where(LedgerMember.ledger_id == ledger_id, LedgerMember.user_id == user.id)
    )
    if member is None:
        # 404, а не 403: посторонний не должен узнать, существует ли такое пространство
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пространство не найдено")
    return member


Membership = Annotated[LedgerMember, Depends(get_membership)]


async def get_manager_membership(member: Membership) -> LedgerMember:
    if member.role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужны права владельца или администратора")
    return member


ManagerMembership = Annotated[LedgerMember, Depends(get_manager_membership)]
