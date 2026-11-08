from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routers import auth, health, ledgers
from app.core.database import engine
from app.services.errors import (
    ConflictError,
    DomainError,
    InvalidDataError,
    NotFoundError,
    PermissionDeniedError,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # До yield — код при старте приложения, после — при остановке
    yield
    await engine.dispose()  # аккуратно закрываем все соединения пула


app = FastAPI(title="Walletly API", version="0.1.0", lifespan=lifespan)

_ERROR_STATUS = {
    NotFoundError: 404,
    PermissionDeniedError: 403,
    ConflictError: 409,
    InvalidDataError: 422,
}


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    # Одно место перевода ошибок сервисов в HTTP вместо try/except в каждом эндпоинте
    return JSONResponse({"detail": exc.message}, status_code=_ERROR_STATUS[type(exc)])


# Единый префикс: фронт и API живут на одном домене, прокси отправляет /api/* в бэкенд.
# Так не нужен CORS, а cookie с SameSite=strict работает без оговорок
api = APIRouter(prefix="/api")
for module in (health, auth, ledgers):
    api.include_router(module.router)
app.include_router(api)
