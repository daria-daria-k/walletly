from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.enums import UserRole

# Email приводим к нижнему регистру: Anna@Mail.ru и anna@mail.ru — один пользователь
NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]


class RegisterRequest(BaseModel):
    """Что клиент присылает при регистрации."""

    email: NormalizedEmail
    # max_length — защита от «пароля» в мегабайт, который Argon2 будет долго хешировать
    password: str = Field(min_length=8, max_length=128)
    # strip_whitespace + min_length: имя из одних пробелов превратится в "" и не пройдёт
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class UserRead(BaseModel):
    """Что API отдаёт о пользователе. password_hash здесь нет — и не должно быть."""

    # Разрешает строить схему из объекта SQLAlchemy: UserRead.model_validate(user)
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: UserRole
    created_at: datetime
