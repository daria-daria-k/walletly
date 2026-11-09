"""Разбор PDF-выписок банка: из строк текста получаем дату, описание и сумму.

Форматы банков различаются, поэтому разбор общий: строка операции начинается с даты,
а заканчивается суммой, иногда ещё и остатком после операции.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

_AMOUNT = r"[+\-−]?\s?\d{1,3}(?:[  ]\d{3})*[.,]\d{2}"
_LINE = re.compile(
    rf"^(?P<date>\d{{2}}\.\d{{2}}\.\d{{2,4}})(?:\s+\d{{2}}:\d{{2}}(?::\d{{2}})?)?\s+"
    rf"(?P<middle>.*?)\s+(?P<amount>{_AMOUNT})(?:\s+(?P<balance>{_AMOUNT}))?(?:\s*(?:RUB|₽|руб\.?))?$"
)


@dataclass(frozen=True)
class StatementLine:
    tx_date: str
    description: str
    amount: Decimal  # меньше нуля — расход


def _to_decimal(text: str) -> Decimal:
    clean = re.sub(r"[\s ]", "", text).replace("−", "-").replace(",", ".")
    return Decimal(clean)


def parse_text(text: str) -> list[StatementLine]:
    lines: list[StatementLine] = []
    for raw in text.splitlines():
        match = _LINE.match(raw.strip())
        if match is None or not match["middle"]:
            continue
        amount = _to_decimal(match["amount"])
        # В выписках расход часто пишут без знака, а поступление всегда с плюсом
        signed = amount if match["amount"].lstrip().startswith("+") else -abs(amount)
        lines.append(StatementLine(match["date"], match["middle"][:500], signed))
    return lines
