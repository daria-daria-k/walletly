from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import health
from app.core.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # До yield — код при старте приложения, после — при остановке
    yield
    await engine.dispose()  # аккуратно закрываем все соединения пула


app = FastAPI(title="Walletly API", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
