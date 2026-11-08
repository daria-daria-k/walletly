"""Служебные команды: uv run python -m app.cli make-admin anna@example.com"""

import asyncio
import sys

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.models import User
from app.models.enums import UserRole


async def make_admin(email: str) -> None:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            sys.exit(f"Пользователь {email} не найден")
        user.role = UserRole.ADMIN
        await session.commit()
    await engine.dispose()
    print(f"{email} теперь администратор")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "make-admin":
        sys.exit("Использование: python -m app.cli make-admin <email>")
    asyncio.run(make_admin(sys.argv[2]))
