from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from app.api.deps import SessionDep
from app.core.config import settings
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    TokenPair,
    authenticate,
    issue_tokens,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
# Браузер отправит cookie только на /auth/* — остальным эндпоинтам refresh не нужен
REFRESH_COOKIE_PATH = "/auth"

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _token_response(response: Response, tokens: TokenPair) -> TokenResponse:
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,  # JavaScript не может прочитать cookie — XSS его не украдёт
        secure=settings.cookie_secure,
        samesite="strict",  # не отправляется при переходе с чужого сайта — защита от CSRF
    )
    return TokenResponse(
        access_token=tokens.access_token, expires_in=settings.access_token_ttl_minutes * 60
    )


def _delete_refresh_cookie(response: Response) -> None:
    # Удалить можно только с тем же path, с которым cookie ставили
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, session: SessionDep) -> UserRead:
    # Роутер переводит ошибки сервиса на язык HTTP — сам сервис про HTTP ничего не знает
    try:
        user = await register_user(session, data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email уже зарегистрирован") from None
    return UserRead.model_validate(user)


@router.post("/login")
async def login(data: LoginRequest, session: SessionDep, response: Response) -> TokenResponse:
    try:
        user = await authenticate(session, data.email, data.password)
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль") from None
    except InactiveUserError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт заблокирован") from None
    return _token_response(response, await issue_tokens(session, user.id))


@router.post("/refresh")
async def refresh(
    session: SessionDep, response: Response, refresh_token: RefreshCookie = None
) -> TokenResponse:
    try:
        if refresh_token is None:
            raise InvalidRefreshTokenError
        tokens = await rotate_refresh_token(session, refresh_token)
    except InvalidRefreshTokenError:
        # Ответ с ошибкой — отдельный объект, поэтому удаление cookie передаём в заголовках
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Сессия истекла, войдите снова",
            headers={"Set-Cookie": _expired_cookie_header()},
        ) from None
    return _token_response(response, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(session: SessionDep, response: Response, refresh_token: RefreshCookie = None) -> None:
    if refresh_token is not None:
        await revoke_refresh_token(session, refresh_token)
    _delete_refresh_cookie(response)


def _expired_cookie_header() -> str:
    response = Response()
    _delete_refresh_cookie(response)
    return response.headers["set-cookie"]
