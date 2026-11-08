from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints

# strip_whitespace + min_length: название из одних пробелов превратится в "" и не пройдёт
Name50 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Name100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

# Совпадает с NUMERIC(12, 2) в БД: лишние цифры отклоняем сразу, а не падаем при записи.
# Decimal уходит в JSON строкой — иначе JavaScript исказил бы сумму, превратив её в float
Money = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
