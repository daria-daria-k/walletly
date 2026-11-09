from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException, Request, Response, status

from app.api.deps import CurrentUser, SessionDep
from app.core import rate_limit
from app.core.config import settings
from app.models.enums import EmailTokenPurpose
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    ResetPasswordRequest,
    SessionsInfo,
    TokenResponse,
    UserProfile,
    UserRead,
    VerifyEmailRequest,
)
from app.services import mailer
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidEmailTokenError,
    InvalidRefreshTokenError,
    TokenPair,
    authenticate,
    change_password,
    count_active_sessions,
    create_email_token,
    current_subscription,
    find_active_user_by_email,
    issue_tokens,
    register_user,
    reset_password,
    revoke_other_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
    update_profile,
    verify_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
# Браузер отправит cookie только на /api/auth/* — остальным эндпоинтам refresh не нужен
REFRESH_COOKIE_PATH = "/api/auth"

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]

LOGIN_WINDOW_SECONDS = 15 * 60
# Связка «адрес + email» ловит подбор одного пароля. Блокировать только по email нельзя:
# тогда любой мог бы закрыть вход чужому аккаунту, просто вводя неверный пароль
LOGIN_LIMIT_PAIR = 10
# Отдельный лимит на адрес ловит перебор многих email. Он выше: за одним адресом бывает целый офис
LOGIN_LIMIT_IP = 100
FORGOT_WINDOW_SECONDS = 60 * 60
FORGOT_LIMIT = 3


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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
async def register(
    data: RegisterRequest, session: SessionDep, background: BackgroundTasks
) -> UserRead:
    # Роутер переводит ошибки сервиса на язык HTTP — сам сервис про HTTP ничего не знает
    try:
        user = await register_user(session, data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email уже зарегистрирован") from None
    token = await create_email_token(session, user.id, EmailTokenPurpose.EMAIL_VERIFICATION)
    # В фоне: пользователь не должен ждать почтовый сервер
    background.add_task(mailer.send_email_verification, user.email, token)
    return UserRead.model_validate(user)


@router.post("/login")
async def login(
    data: LoginRequest, session: SessionDep, request: Request, response: Response
) -> TokenResponse:
    ip = _client_ip(request)
    ip_key = f"login:ip:{ip}"
    pair_key = f"login:pair:{ip}:{data.email}"
    if await rate_limit.is_blocked(pair_key, LOGIN_LIMIT_PAIR) or await rate_limit.is_blocked(
        ip_key, LOGIN_LIMIT_IP
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много попыток. Попробуйте через 15 минут"
        )
    try:
        user = await authenticate(session, data.email, data.password)
    except InvalidCredentialsError:
        await rate_limit.hit(pair_key, LOGIN_WINDOW_SECONDS)
        await rate_limit.hit(ip_key, LOGIN_WINDOW_SECONDS)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль") from None
    except InactiveUserError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт заблокирован") from None
    await rate_limit.clear(pair_key)
    return _token_response(response, await issue_tokens(session, user.id))


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    data: ForgotPasswordRequest, session: SessionDep, background: BackgroundTasks
) -> None:
    # Ответ всегда одинаковый: по нему нельзя узнать, кто зарегистрирован
    key = f"forgot:{data.email}"
    if await rate_limit.is_blocked(key, FORGOT_LIMIT):
        return
    await rate_limit.hit(key, FORGOT_WINDOW_SECONDS)
    user = await find_active_user_by_email(session, data.email)
    if user is not None:
        token = await create_email_token(session, user.id, EmailTokenPurpose.PASSWORD_RESET)
        background.add_task(mailer.send_password_reset, user.email, token)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_my_password(data: ResetPasswordRequest, session: SessionDep) -> None:
    try:
        await reset_password(session, data.token, data.new_password)
    except InvalidEmailTokenError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Ссылка устарела. Запросите новую"
        ) from None


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_my_email(data: VerifyEmailRequest, session: SessionDep) -> None:
    try:
        await verify_email(session, data.token)
    except InvalidEmailTokenError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Ссылка устарела. Отправьте письмо ещё раз"
        ) from None


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(
    user: CurrentUser, session: SessionDep, background: BackgroundTasks
) -> None:
    if user.email_verified_at is not None:
        return
    key = f"verify:{user.id}"
    if await rate_limit.is_blocked(key, FORGOT_LIMIT):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Письмо уже отправлено, проверьте почту")
    await rate_limit.hit(key, FORGOT_WINDOW_SECONDS)
    token = await create_email_token(session, user.id, EmailTokenPurpose.EMAIL_VERIFICATION)
    background.add_task(mailer.send_email_verification, user.email, token)


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


@router.get("/me")
async def me(user: CurrentUser, session: SessionDep) -> UserProfile:
    subscription = await current_subscription(session, user.id)
    return UserProfile(
        **UserRead.model_validate(user).model_dump(),
        plan=subscription.plan,
        plan_expires_at=subscription.expires_at,
    )


@router.patch("/me")
async def update_me(data: ProfileUpdate, user: CurrentUser, session: SessionDep) -> UserRead:
    return UserRead.model_validate(await update_profile(session, user, data))


@router.get("/sessions")
async def sessions(user: CurrentUser, session: SessionDep) -> SessionsInfo:
    return SessionsInfo(active=await count_active_sessions(session, user.id))


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_others(
    user: CurrentUser, session: SessionDep, refresh_token: RefreshCookie = None
) -> None:
    # Без cookie нельзя понять, какая сессия текущая, и отозвали бы все
    if refresh_token is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Текущая сессия не определена")
    await revoke_other_sessions(session, user.id, refresh_token)


@router.post("/change-password")
async def change_my_password(
    data: ChangePasswordRequest, user: CurrentUser, session: SessionDep, response: Response
) -> TokenResponse:
    try:
        tokens = await change_password(session, user, data.current_password, data.new_password)
    except InvalidCredentialsError:
        # 400, а не 401: сессия действительна, неверно только поле формы.
        # На 401 фронт попытался бы обновить токен и выкинул пользователя на вход
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный текущий пароль") from None
    return _token_response(response, tokens)


def _expired_cookie_header() -> str:
    response = Response()
    _delete_refresh_cookie(response)
    return response.headers["set-cookie"]
