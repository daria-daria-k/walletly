"""Разбор выписок банков: из PDF или таблицы получаем дату, описание и сумму.

Правила привязаны к виду строки, а не к банку: один банк со временем меняет оформление,
а разные банки часто оформляют строки одинаково. Банк определяем для показа пользователю.
Точных образцов большинства PDF у нас нет, поэтому результат сверяется с итогами самой выписки.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.services.errors import InvalidDataError

_DATE = r"(?:\d{2}\.\d{2}\.\d{2,4}|\d{4}-\d{2}-\d{2})"
_TIME = r"\d{2}:\d{2}(?::\d{2})?"
_MONEY = r"[+\-−]?\s?\d{1,3}(?:[  ]\d{3})*[.,]\d{2}"
_CURRENCY = r"(?:RUB|RUR|₽|руб\.?|р\.)"
_DATES = rf"(?P<date>{_DATE})(?:\s+{_TIME})?(?:\s+{_DATE}(?:\s+{_TIME})?)?"

# Обычная строка: дата, описание, сумма и иногда остаток после операции
_LINE = re.compile(
    rf"^{_DATES}\s+(?P<middle>.*?)\s+(?P<amount>{_MONEY})(?:\s*{_CURRENCY})?"
    rf"(?:\s+(?P<balance>{_MONEY})(?:\s*{_CURRENCY})?)?$"
)
# Суммы перед описанием. Если их две, вторая — в валюте карты: она и списана со счёта
_AMOUNTS_FIRST = re.compile(
    rf"^{_DATES}\s+(?P<first>{_MONEY})\s*{_CURRENCY}"
    rf"(?:\s+(?P<second>{_MONEY})\s*{_CURRENCY})?\s+(?P<text>.+)$"
)
_CARD_DIGITS = re.compile(r"\s+\d{4}$")
_TIME_LINE = re.compile(rf"^{_TIME}(?:\s+{_TIME})*\s*(?P<text>.*)$")

# Сбер пишет операцию двумя строками: в первой дата, своя категория и суммы,
# во второй дата обработки, код авторизации и настоящее описание операции
_DETAIL = re.compile(r"^\d{2}\.\d{2}\.\d{2,4}\s+\d{6}\s+(?P<text>.+)$")
# Хвост с номером карты: описанию он только мешает, а хранить его незачем
_CARD_TAIL = re.compile(r"\.?\s*Операция по\b.*$", re.IGNORECASE)

_STARTS_WITH_DATE = re.compile(rf"^{_DATE}\b")
_SUMMARY = re.compile(r"итог|всего|пополнени|поступлени|зачислени|приход|списани|расход", re.IGNORECASE)

_BANKS = (
    ("Сбер", r"сбербанк|sberbank|(?<!\w)сбер(?!\w)"),
    ("Т-Банк", r"(?<!\w)т[-‑]?банк|тинькофф|tinkoff|t-bank"),
    ("Альфа-Банк", r"альфа[-‑ ]?банк|alfa[-‑ ]?bank"),
    ("ВТБ", r"(?<!\w)втб(?!\w)|(?<!\w)vtb(?!\w)"),
    ("Райффайзен", r"райффайзен|raiffeisen"),
    ("Газпромбанк", r"газпромбанк|gazprombank"),
    ("Озон Банк", r"озон[ -]?банк|ozon[ -]?bank"),
    ("Яндекс Банк", r"яндекс[ -]?банк|yandex[ -]?bank"),
    ("Совкомбанк", r"совкомбанк|sovcombank"),
    ("Почта Банк", r"почта[ -]?банк"),
    ("МКБ", r"московский кредитный банк"),
    ("Россельхозбанк", r"россельхозбанк"),
    ("Хлынов", r"хлынов"),
)
# Название ищем только в шапке: ниже оно встречается в переводах («Перевод в Сбербанк»)
_HEADER_LINES = 25


@dataclass(frozen=True)
class StatementLine:
    tx_date: str
    description: str
    amount: Decimal  # меньше нуля — расход


@dataclass(frozen=True)
class ParsedStatement:
    bank: str | None
    lines: list[StatementLine]
    # True и False — итоги найдены и сошлись или нет. None — сверять не с чем
    reconciled: bool | None = None

    @property
    def income(self) -> Decimal:
        return sum((line.amount for line in self.lines if line.amount > 0), Decimal(0))

    @property
    def expense(self) -> Decimal:
        return sum((-line.amount for line in self.lines if line.amount < 0), Decimal(0))


def _to_decimal(text: str) -> Decimal:
    clean = re.sub(r"[\s ]", "", text).replace("−", "-").replace(",", ".")
    return Decimal(clean)


def _signed(raw: str) -> Decimal:
    # В выписках расход часто пишут без знака, а поступление всегда с плюсом
    amount = _to_decimal(raw)
    return amount if raw.lstrip().startswith("+") else -abs(amount)


def _description(middle: str, next_line: str) -> str:
    detail = _DETAIL.match(next_line)
    if detail is None:
        return middle
    return _CARD_TAIL.sub("", detail["text"]).strip() or middle


def _amounts_first(match: re.Match[str], next_line: str) -> StatementLine:
    text = _CARD_DIGITS.sub("", match["text"]).strip()
    # Вторая строка такой операции начинается со времени, остаток — перенос описания
    wrapped = _TIME_LINE.match(next_line)
    if wrapped is not None and wrapped["text"]:
        text = f"{text} {wrapped['text']}"
    return StatementLine(match["date"], text[:500], _signed(match["second"] or match["first"]))


def parse_text(text: str) -> list[StatementLine]:
    rows = [raw.strip() for raw in text.splitlines()]
    lines: list[StatementLine] = []
    for index, row in enumerate(rows):
        next_line = rows[index + 1] if index + 1 < len(rows) else ""
        first = _AMOUNTS_FIRST.match(row)
        if first is not None:
            lines.append(_amounts_first(first, next_line))
            continue
        match = _LINE.match(row)
        if match is None or not match["middle"]:
            continue
        lines.append(
            StatementLine(match["date"], _description(match["middle"], next_line)[:500], _signed(match["amount"]))
        )
    return lines


def detect_bank(text: str) -> str | None:
    header = "\n".join(text.splitlines()[:_HEADER_LINES]).lower()
    # Первое упоминание: банк-эмитент указан раньше контрагентов и партнёров
    found = [(match.start(), name) for name, rule in _BANKS if (match := re.search(rule, header))]
    return min(found)[1] if found else None


def _reconcile(text: str, statement_lines: list[StatementLine]) -> bool | None:
    totals: set[Decimal] = set()
    for raw in text.splitlines():
        row = raw.strip()
        if _SUMMARY.search(row) and not _STARTS_WITH_DATE.match(row):
            totals |= {abs(_to_decimal(found)) for found in re.findall(_MONEY, row)}
    if not totals:
        return None
    parsed = ParsedStatement(None, statement_lines)
    return all(value == 0 or value in totals for value in (parsed.income, parsed.expense))


def parse_pdf_text(text: str) -> ParsedStatement:
    lines = parse_text(text)
    return ParsedStatement(detect_bank(text), lines, _reconcile(text, lines))


def _cell(cells: list[object], index: int) -> str:
    value = cells[index] if index < len(cells) else None
    return "" if value is None else str(value).strip()


def _table_amount(number: int, text: str) -> Decimal:
    try:
        return _to_decimal(text or "0")
    except InvalidOperation:
        raise InvalidDataError(f"Строка {number}: неверная сумма") from None


def _named(header: list[object]) -> dict[str, int]:
    return {str(cell or "").strip().lower(): index for index, cell in enumerate(header)}


def _tbank(table: list[list], columns: dict[str, int]) -> ParsedStatement:
    lines = []
    for number, cells in table:
        # Неуспешные операции банк показывает в выгрузке, но денег они не двигали
        if _cell(cells, columns["статус"]).upper() != "OK":
            continue
        amount = _table_amount(number, _cell(cells, columns["сумма платежа"]))
        if amount:
            when = _cell(cells, columns["дата операции"]).split(" ")[0]
            lines.append(StatementLine(when, _cell(cells, columns["описание"])[:500], amount))
    return ParsedStatement("Т-Банк", lines)


def _alfa(table: list[list], columns: dict[str, int]) -> ParsedStatement:
    lines = []
    for number, cells in table:
        income = _table_amount(number, _cell(cells, columns["приход"]))
        amount = income or -abs(_table_amount(number, _cell(cells, columns["расход"])))
        if amount:
            lines.append(
                StatementLine(
                    _cell(cells, columns["дата операции"]),
                    _cell(cells, columns["описание операции"])[:500],
                    amount,
                )
            )
    return ParsedStatement("Альфа-Банк", lines)


def _is_iso_moment(text: str) -> bool:
    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return True


def _vtb(table: list[list]) -> ParsedStatement | None:
    # В файле ВТБ несколько блоков: период, счёт, баланс. Операции узнаём по дате со временем
    lines = []
    for number, cells in table:
        if len(cells) < 8 or not _is_iso_moment(_cell(cells, 1)):
            continue
        amount = _table_amount(number, _cell(cells, 5))
        if amount:
            text = re.sub(r"^Карта \*\d*\s*", "", _cell(cells, 7))
            lines.append(StatementLine(_cell(cells, 1).split(" ")[0], text[:500], amount))
    return ParsedStatement("ВТБ", lines) if lines else None


def parse_table(table: list[list]) -> ParsedStatement | None:
    """Узнаёт выгрузку банка по колонкам. None — это не выгрузка банка, а наш шаблон."""
    if not table:
        return None
    columns = _named(table[0][1])
    if {"статус", "сумма платежа", "дата операции", "описание"} <= set(columns):
        return _tbank(table[1:], columns)
    if {"приход", "расход", "дата операции", "описание операции"} <= set(columns):
        return _alfa(table[1:], columns)
    return _vtb(table)
