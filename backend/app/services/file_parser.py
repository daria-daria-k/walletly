"""Разбор файла пользователя. Запускается отдельным процессом: python -m app.services.file_parser xlsx

Файл присылает кто угодно, и библиотеки разбора не защищены от специально собранных файлов:
3 МБ могут развернуться в гигабайты. Поэтому модуль импортирует только библиотеки разбора
и не знает про настройки приложения, а ответ отдаёт в JSON: его нельзя превратить в код,
в отличие от pickle, даже если разбор будет взломан.
"""

import csv
import io
import json
import resource
import sys
import zipfile
from datetime import date, datetime, time

MAX_ROWS = 5000
MAX_PAGES = 100
# Пустые строки тоже стоят времени: openpyxl дополняет пропуски в нумерации, и файл на 4 КБ
# с единственной строкой под номером 2 000 000 000 разбирался бы часами.
# Данные ниже этой строки игнорируются: заполненных строк всё равно разрешено меньше
MAX_SCAN_ROWS = 20_000
MAX_COLUMNS = 50
MAX_UNPACKED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 200

_MEMORY_LIMIT_BYTES = 640 * 1024 * 1024
_CPU_LIMIT_SECONDS = 25


class FileRejected(Exception):
    """Файл понятен, но нарушает ограничения: текст показываем пользователю."""


def _limit_resources() -> None:
    limits = (
        (resource.RLIMIT_AS, _MEMORY_LIMIT_BYTES),
        (resource.RLIMIT_CPU, _CPU_LIMIT_SECONDS),
        # Разбору незачем писать на диск
        (resource.RLIMIT_FSIZE, 0),
    )
    for name, value in limits:
        try:
            resource.setrlimit(name, (value, value))
        except (ValueError, OSError):
            # macOS отклоняет часть лимитов. На сервере, в Linux-контейнере, они работают
            pass


def _check_archive(content: bytes) -> None:
    # Размер берём из заголовков: zipfile не отдаст больше объявленного, поэтому занизить
    # его в заголовке и получить больше данных не выйдет
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_ENTRIES or sum(e.file_size for e in entries) > MAX_UNPACKED_BYTES:
        raise FileRejected("Файл слишком большой после распаковки")


def _cell(value: object) -> object:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return str(value)
    return value


def _xlsx_rows(content: bytes):
    from openpyxl import load_workbook

    _check_archive(content)
    # read_only — потоковое чтение: большой лист не загружается в память целиком
    sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).worksheets[0]
    rows = sheet.iter_rows(max_row=MAX_SCAN_ROWS, max_col=MAX_COLUMNS, values_only=True)
    return enumerate(rows, start=1)


def _csv_rows(content: bytes):
    # utf-8-sig: Excel сохраняет CSV с BOM, иначе он приклеится к первому заголовку
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Т-Банк, Альфа и ВТБ выгружают CSV в кодировке Windows
        text = content.decode("cp1251")
    # Первая строка выгрузки ВТБ бывает без разделителей, поэтому берём первую, где они есть
    sample = next((line for line in text.splitlines()[:10] if ";" in line or "," in line), "")
    delimiter = ";" if ";" in sample else ","
    return enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1)


def _table(rows) -> dict:
    """Возвращает пары (номер строки в файле, ячейки), включая заголовок."""
    result: list[list[object]] = []
    for number, cells in rows:
        if all(cell is None or str(cell).strip() == "" for cell in cells):
            continue
        result.append([number, [_cell(cell) for cell in cells]])
        # +1 на заголовок
        if len(result) > MAX_ROWS + 1:
            raise FileRejected(f"В файле больше {MAX_ROWS} строк")
    return {"rows": result}


def _pdf(content: bytes) -> dict:
    # Импорт занимает около секунды, таблицам он не нужен
    import pdfplumber

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) > MAX_PAGES:
            raise FileRejected(f"В выписке больше {MAX_PAGES} страниц")
        return {"text": "\n".join(page.extract_text() or "" for page in pdf.pages)}


def parse(kind: str, content: bytes) -> dict:
    if kind == "pdf":
        return _pdf(content)
    return _table(_csv_rows(content) if kind == "csv" else _xlsx_rows(content))


def main() -> int:
    kind = sys.argv[1]
    content = sys.stdin.buffer.read()
    _limit_resources()
    try:
        result = parse(kind, content)
    except FileRejected as exc:
        result = {"error": str(exc)}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
