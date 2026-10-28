import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

JWT_ALGORITHM = "HS256"

# recommended() — Argon2id с параметрами, которые авторы pwdlib считают безопасными сейчас
_password_hash = PasswordHash.recommended()


# --- Пароли ---
# Argon2 намеренно медленный (~десятки мс CPU). В async-коде вызывать через
# run_in_threadpool, иначе он заблокирует event loop


def hash_password(password: str) -> str:
    """Хеш со случайной солью: у одинаковых паролей разные хеши."""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


# --- Access-токен (JWT) ---


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # subject — чей токен; по стандарту JWT это строка
        "type": "access",
        "iat": now,  # issued at — когда выдан
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Возвращает user_id. При неверной подписи, истёкшем сроке или чужом типе — jwt.InvalidTokenError."""
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        # Список разрешённых алгоритмов обязателен: иначе атакующий может прислать
        # токен с "alg": "none" (без подписи), и такой токен прошёл бы проверку
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "exp"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return int(payload["sub"])


# --- Refresh-токен ---
# Это не JWT, а просто случайная строка: вся информация о нём хранится в БД


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)  # 32 байта из криптостойкого генератора


def hash_refresh_token(token: str) -> str:
    """SHA-256, а не Argon2: токен и так случайный и длинный, подбирать его бессмысленно."""
    return hashlib.sha256(token.encode()).hexdigest()
