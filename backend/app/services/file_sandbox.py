"""Запуск разбора файла в отдельном процессе с лимитами памяти и времени."""

import asyncio
import json
import os
import sys
from pathlib import Path

from app.core.limits import BusyLimiter
from app.services.errors import InvalidDataError

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_TIMEOUT_SECONDS = 30
# Только PATH: разбору незачем видеть пароль базы и секрет JWT из окружения приложения
_CHILD_ENV = {"PATH": os.environ.get("PATH", "")}
_UNREADABLE = {
    "xlsx": "Не удалось прочитать файл. Нужен .xlsx или .csv",
    "csv": "Не удалось прочитать файл. Нужен .xlsx или .csv",
    "pdf": "Не удалось прочитать PDF",
}

# Каждый разбор может занять до 640 МБ, поэтому одновременно идут только два
_slots = BusyLimiter(2, 20, "Сейчас обрабатывается много файлов. Попробуйте через минуту")


async def run(kind: str, content: bytes) -> dict:
    async with _slots.slot():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.services.file_parser",
            kind,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=_BACKEND_DIR,
            env=_CHILD_ENV,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(content), _TIMEOUT_SECONDS)
        except TimeoutError:
            raise InvalidDataError("Файл слишком сложный, разбор занял слишком много времени") from None
        finally:
            # В том числе если клиент оборвал запрос: процесс не должен работать впустую
            if process.returncode is None:
                process.kill()
                await process.wait()

    # Ненулевой код — процесс упал, в том числе превысил лимит памяти или процессора
    if process.returncode != 0:
        raise InvalidDataError(_UNREADABLE[kind])
    result = json.loads(output)
    if "error" in result:
        raise InvalidDataError(result["error"])
    return result
