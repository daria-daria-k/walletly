from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.enums import Plan, UserRole

# Email приводим к нижнему регистру: Anna@Mail.ru и anna@mail.ru — один пользователь
NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]


class RegisterRequest(BaseModel):
    """Что клиент присылает при регистрации."""

    email: NormalizedEmail
    # max_length — защита от «пароля» в мегабайт, который Argon2 будет долго хешировать
    password: str = Field(min_length=8, max_length=128)
    # strip_whitespace + min_length: имя из одних пробелов превратится в "" и не пройдёт
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class LoginRequest(BaseModel):
    email: NormalizedEmail
    # Без min_length: старые правила пароля могли быть мягче — не мешаем таким входить
    password: str = Field(max_length=128)


class NotificationSettings(BaseModel):
    budget: bool = True
    unusual: bool = True
    weekly: bool = True
    family: bool = True


class ProfileUpdate(BaseModel):
    # default=None при типе без None: поле можно не передавать, а явный null — ошибка 422
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] = Field(default=None)
    onboarding_completed: bool = Field(default=None)
    notifications: NotificationSettings = Field(default=None)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: NormalizedEmail


class ResetPasswordRequest(BaseModel):
    token: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str = Field(max_length=128)


class TokenResponse(BaseModel):
    """Access-токен в теле ответа. Refresh сюда не попадает — он уходит в httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # через сколько секунд истечёт access-токен


class UserRead(BaseModel):
    """Что API отдаёт о пользователе. password_hash здесь нет — и не должно быть."""

    # Разрешает строить схему из объекта SQLAlchemy: UserRead.model_validate(user)
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: UserRole
    onboarding_completed: bool
    notifications: NotificationSettings
    email_verified_at: datetime | None
    created_at: datetime


class UserProfile(UserRead):
    """Текущий пользователь: интерфейсу нужен ещё и тариф."""

    plan: Plan
    plan_expires_at: datetime | None  # None — бессрочно


class SessionsInfo(BaseModel):
    active: int
