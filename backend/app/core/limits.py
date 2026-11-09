"""Ограничение числа одновременных тяжёлых операций."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.services.errors import TooBusyError


class BusyLimiter:
    """Пропускает ограниченное число задач, остальные ждут в очереди.

    Без него сотня одновременных запросов съела бы всю память сервера. Ожидание ограничено
    по времени: лучше честно ответить «занято», чем копить запросы бесконечно.
    """

    def __init__(self, slots: int, wait_seconds: float, busy_message: str) -> None:
        self._semaphore = asyncio.Semaphore(slots)
        self._wait_seconds = wait_seconds
        self._busy_message = busy_message

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        try:
            async with asyncio.timeout(self._wait_seconds):
                await self._semaphore.acquire()
        except TimeoutError:
            raise TooBusyError(self._busy_message) from None
        try:
            yield
        finally:
            self._semaphore.release()
