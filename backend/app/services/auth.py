from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, or_, select, update
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
    EmailToken,
    Ledger,
    LedgerMember,
    RefreshToken,
    Subscription,
    User,
)
from app.models.enums import EmailTokenPurpose, LedgerType, MemberRole, Plan
from app.schemas.auth import ProfileUpdate, RegisterRequest
from app.services.ledger import add_default_categories


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Неверный email или пароль — намеренно без уточнения, что именно."""


class InactiveUserError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


class InvalidEmailTokenError(Exception):
    pass


_EMAIL_TOKEN_TTL = {
    EmailTokenPurpose.PASSWORD_RESET: timedelta(hours=1),
    EmailTokenPurpose.EMAIL_VERIFICATION: timedelta(days=7),
}


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

    await add_default_categories(session, ledger.id)

    try:
        await session.commit()
    except IntegrityError:
        # Два одновременных запроса с одним email могли оба пройти проверку выше.
        # Уникальный индекс в БД пропустит только первый — второй упадёт здесь
        await session.rollback()
        raise EmailAlreadyRegisteredError from None

    return user


# --- Профиль ---


async def current_subscription(session: AsyncSession, user_id: int) -> Subscription:
    return await session.scalar(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.id.desc())
        .limit(1)
    )


async def update_profile(session: AsyncSession, user: User, data: ProfileUpdate) -> User:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    return user


async def change_password(
    session: AsyncSession, user: User, current_password: str, new_password: str
) -> TokenPair:
    """Меняет пароль и завершает все сессии: если пароль утёк, вор потеряет доступ."""
    if not await run_in_threadpool(verify_password, current_password, user.password_hash):
        raise InvalidCredentialsError
    user.password_hash = await run_in_threadpool(hash_password, new_password)
    await revoke_all_refresh_tokens(session, user.id)
    return await issue_tokens(session, user.id)


# --- Ссылки из писем ---


async def create_email_token(
    session: AsyncSession, user_id: int, purpose: EmailTokenPurpose
) -> str:
    """Новая ссылка отменяет предыдущие того же назначения: действует только последнее письмо."""
    now = datetime.now(UTC)
    await session.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    token = generate_refresh_token()
    session.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_refresh_token(token),
            expires_at=now + _EMAIL_TOKEN_TTL[purpose],
        )
    )
    await session.commit()
    return token


async def _consume_email_token(
    session: AsyncSession, token: str, purpose: EmailTokenPurpose
) -> User:
    """Без commit: отметка об использовании фиксируется вместе с самим действием."""
    now = datetime.now(UTC)
    stored = await session.scalar(
        select(EmailToken)
        .where(EmailToken.token_hash == hash_refresh_token(token), EmailToken.purpose == purpose)
        # Блокировка: два одновременных запроса не смогут использовать ссылку дважды
        .with_for_update()
    )
    if stored is None or stored.used_at is not None or stored.expires_at <= now:
        raise InvalidEmailTokenError
    stored.used_at = now
    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise InvalidEmailTokenError
    return user


async def find_active_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email, User.is_active.is_(True)))


async def reset_password(session: AsyncSession, token: str, new_password: str) -> None:
    user = await _consume_email_token(session, token, EmailTokenPurpose.PASSWORD_RESET)
    user.password_hash = await run_in_threadpool(hash_password, new_password)
    # Сброс часто означает, что доступ потерян или украден, — закрываем все устройства
    await revoke_all_refresh_tokens(session, user.id)
    # Письмо пришло на этот адрес, значит, он настоящий
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    await session.commit()


async def verify_email(session: AsyncSession, token: str) -> None:
    user = await _consume_email_token(session, token, EmailTokenPurpose.EMAIL_VERIFICATION)
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    await session.commit()


async def delete_stale_tokens(session: AsyncSession) -> int:
    """Запускается по расписанию: истёкшие токены больше ни для чего не нужны."""
    now = datetime.now(UTC)
    refresh = await session.execute(delete(RefreshToken).where(RefreshToken.expires_at <= now))
    email = await session.execute(
        delete(EmailToken).where(or_(EmailToken.expires_at <= now, EmailToken.used_at.is_not(None)))
    )
    await session.commit()
    return refresh.rowcount + email.rowcount


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


async def revoke_all_refresh_tokens(session: AsyncSession, user_id: int) -> None:
    """Без commit: вызывающий код фиксирует отзыв вместе со своими изменениями."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def count_active_sessions(session: AsyncSession, user_id: int) -> int:
    # При ротации старый токен отзывается, поэтому действующий токен — это одно устройство
    return await session.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )


async def revoke_other_sessions(session: AsyncSession, user_id: int, refresh_token: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.token_hash != hash_refresh_token(refresh_token),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()


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
        await revoke_all_refresh_tokens(session, stored.user_id)
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
