from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import (
    Category,
    CategoryGroup,
    Ledger,
    LedgerMember,
    RefreshToken,
    Subscription,
    User,
)
from app.models.enums import LedgerType, MemberRole, Plan
from app.schemas.auth import RegisterRequest
from app.services.category_template import DEFAULT_CATEGORY_GROUPS


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Неверный email или пароль — намеренно без уточнения, что именно."""


class InactiveUserError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


# --- Регистрация ---


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


# --- Вход ---


@cache
def _dummy_password_hash() -> str:
    return hash_password("dummy-password-for-timing")


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email.lower()))

    # Пароль проверяем, даже если пользователя нет. Иначе ответ для незнакомого email
    # придёт на ~50 мс быстрее, и по времени можно выяснить, кто зарегистрирован
    password_hash = user.password_hash if user else _dummy_password_hash()
    password_ok = await run_in_threadpool(verify_password, password, password_hash)

    if user is None or not password_ok:
        raise InvalidCredentialsError
    # О блокировке сообщаем только после верного пароля
    if not user.is_active:
        raise InactiveUserError
    return user


# --- Токены ---


async def issue_tokens(session: AsyncSession, user_id: int) -> TokenPair:
    refresh_token = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    await session.commit()
    return TokenPair(access_token=create_access_token(user_id), refresh_token=refresh_token)


async def rotate_refresh_token(session: AsyncSession, refresh_token: str) -> TokenPair:
    """Обменивает refresh-токен на новую пару. Старый refresh становится недействительным."""
    now = datetime.now(UTC)
    stored = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
        # Блокировка строки: два одновременных запроса с одним токеном
        # выполнятся по очереди, и второй увидит, что токен уже отозван
        .with_for_update()
    )
    if stored is None:
        raise InvalidRefreshTokenError

    if stored.revoked_at is not None:
        # Отозванный токен предъявили повторно — значит, его копия у кого-то ещё.
        # Мы не знаем, у кого настоящий — завершаем все сессии пользователя
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == stored.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.commit()
        raise InvalidRefreshTokenError

    user = await session.get(User, stored.user_id)
    if stored.expires_at <= now or not user.is_active:
        raise InvalidRefreshTokenError

    stored.revoked_at = now
    # issue_tokens делает commit — отзыв старого и выдача нового фиксируются вместе
    return await issue_tokens(session, stored.user_id)


async def revoke_refresh_token(session: AsyncSession, refresh_token: str) -> None:
    """Выход. Повторный вызов с тем же токеном ничего не ломает."""
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
