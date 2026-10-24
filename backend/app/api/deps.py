from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session

# Короткий псевдоним: в эндпоинте пишем `session: SessionDep` вместо полной записи Depends
SessionDep = Annotated[AsyncSession, Depends(get_session)]
