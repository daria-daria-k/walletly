from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep
from app.schemas.auth import RegisterRequest, UserRead
from app.services.auth import EmailAlreadyRegisteredError, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, session: SessionDep) -> UserRead:
    # Роутер переводит ошибки сервиса на язык HTTP — сам сервис про HTTP ничего не знает
    try:
        user = await register_user(session, data)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email уже зарегистрирован") from None
    return UserRead.model_validate(user)
