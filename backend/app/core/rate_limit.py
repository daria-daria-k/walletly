"""Счётчики попыток в Redis: сколько раз за окно времени что-то случилось."""

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis, а не память процесса: воркеров может быть несколько, и счётчик должен быть общим
_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)


def set_client(client: Redis) -> None:
    """Тесты подменяют настоящий Redis на встроенную имитацию."""
    global _client
    _client = client


async def is_blocked(key: str, limit: int) -> bool:
    try:
        value = await _client.get(key)
    except RedisError:
        # Если Redis упал, лучше временно пустить без лимита, чем не пускать никого.
        # От подбора при этом всё равно защищает медленный Argon2
        logger.exception("Redis недоступен, проверка лимита пропущена")
        return False
    return value is not None and int(value) >= limit


async def hit(key: str, window_seconds: int) -> None:
    try:
        # Счётчик и срок жизни ставим одной транзакцией: иначе при сбое между командами
        # ключ остался бы без срока и заблокировал бы навсегда
        async with _client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window_seconds, nx=True)
            await pipe.execute()
    except RedisError:
        logger.exception("Redis недоступен, попытка не посчитана")


async def set_value(key: str, value: str, ttl_seconds: int) -> None:
    await _client.set(key, value, ex=ttl_seconds)


async def pop_value(key: str) -> str | None:
    """GETDEL одной командой: два одновременных запроса не смогут использовать код дважды."""
    return await _client.getdel(key)


async def clear(key: str) -> None:
    try:
        await _client.delete(key)
    except RedisError:
        logger.exception("Redis недоступен, счётчик не сброшен")
