from typing import Annotated

from pydantic import StringConstraints

# strip_whitespace + min_length: название из одних пробелов превратится в "" и не пройдёт
Name50 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Name100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
