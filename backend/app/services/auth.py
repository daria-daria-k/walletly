from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import Category, CategoryGroup, Ledger, LedgerMember, Subscription, User
from app.models.enums import LedgerType, MemberRole, Plan
from app.schemas.auth import RegisterRequest
from app.services.category_template import DEFAULT_CATEGORY_GROUPS


class EmailAlreadyRegisteredError(Exception):
    pass


async def register_user(session: AsyncSession, data: RegisterRequest) -> User:
    """Создаёт пользователя вместе с личным пространством, подпиской и шаблоном категорий.

    Всё в одной транзакции БД: при любой ошибке не останется «половины» пользователя.
    """
    # Быстрая проверка, чтобы не тратить время на Argon2 впустую
    if await session.scalar(select(User.id).where(User.email == data.email)):
        raise EmailAlreadyRegisteredError

    # Argon2 нагружает CPU — выносим в отдельный поток, чтобы не блокировать event loop
    password_hash = await run_in_threadpool(hash_password, data.password)

    user = User(email=data.email, password_hash=password_hash, name=data.name)
    ledger = Ledger(name="Личное", type=LedgerType.PERSONAL, owner=user)
    session.add_all(
        [
            user,
            ledger,
            LedgerMember(ledger=ledger, user=user, role=MemberRole.OWNER),
            Subscription(user=user, plan=Plan.FREE),
        ]
    )
    # flush отправляет INSERT-ы в БД, но не завершает транзакцию —
    # так мы получаем ledger.id для категорий, а откатить всё ещё можно
    await session.flush()

    for group_order, (group_name, category_type, category_names) in enumerate(
        DEFAULT_CATEGORY_GROUPS
    ):
        group = CategoryGroup(
            ledger_id=ledger.id, name=group_name, type=category_type, sort_order=group_order
        )
        group.categories = [
            Category(ledger_id=ledger.id, name=name, sort_order=order)
            for order, name in enumerate(category_names)
        ]
        session.add(group)

    try:
        await session.commit()
    except IntegrityError:
        # Два одновременных запроса с одним email могли оба пройти проверку выше.
        # Уникальный индекс в БД пропустит только первый — второй упадёт здесь
        await session.rollback()
        raise EmailAlreadyRegisteredError from None

    return user
