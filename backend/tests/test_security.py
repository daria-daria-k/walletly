from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def make_token(secret: str = settings.jwt_secret, **overrides) -> str:
    """JWT с произвольным содержимым — чтобы проверить, что плохие токены отклоняются."""
    payload = {
        "sub": "42",
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    } | overrides
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


# --- Пароли ---


def test_hash_is_not_password_and_verifies() -> None:
    hashed = hash_password("s3cret-pass")

    assert hashed != "s3cret-pass"
    assert hashed.startswith("$argon2id$")
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong-pass", hashed)


def test_same_password_gives_different_hashes() -> None:
    assert hash_password("same") != hash_password("same")


# --- Access-токен ---


def test_access_token_roundtrip() -> None:
    token = create_access_token(user_id=42)

    assert decode_access_token(token) == 42


def test_expired_token_rejected() -> None:
    token = make_token(exp=datetime.now(UTC) - timedelta(seconds=1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_other_secret_rejected() -> None:
    token = make_token(secret="x" * 32)

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_tampered_payload_rejected() -> None:
    header, _, signature = create_access_token(user_id=42).split(".")
    # Подменяем данные на {"sub": "1"} от другого пользователя, подпись оставляем старую
    forged_payload = jwt.utils.base64url_encode(b'{"sub":"1","type":"access","exp":9999999999}')
    forged = f"{header}.{forged_payload.decode()}.{signature}"

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_unsigned_token_rejected() -> None:
    token = jwt.encode({"sub": "42", "type": "access", "exp": 9999999999}, None, algorithm="none")

    with pytest.raises(jwt.InvalidAlgorithmError):
        decode_access_token(token)


def test_wrong_token_type_rejected() -> None:
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(make_token(type="refresh"))


# --- Refresh-токен ---


def test_refresh_tokens_are_unique_and_hash_is_stable() -> None:
    token = generate_refresh_token()

    assert token != generate_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert len(hash_refresh_token(token)) == 64
