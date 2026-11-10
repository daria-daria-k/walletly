from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CategoryType
from app.schemas.common import Name50, PositiveMoney


class CategoryGroupCreate(BaseModel):
    name: Name50
    type: CategoryType
    sort_order: int = 0


class CategoryGroupUpdate(BaseModel):
    # Типа нет намеренно: он определяет, какие операции допустимы в категориях группы
    name: Name50 = Field(default=None)
    sort_order: int = Field(default=None)


class CategoryCreate(BaseModel):
    category_group_id: int
    name: Name50
    monthly_limit: PositiveMoney | None = None
    icon_key: str | None = Field(default=None, max_length=50)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    category_group_id: int = Field(default=None)
    name: Name50 = Field(default=None)
    # null здесь осмысленный: снять лимит
    monthly_limit: PositiveMoney | None = None
    icon_key: str | None = Field(default=None, max_length=50)
    is_active: bool = Field(default=None)
    sort_order: int = Field(default=None)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_group_id: int
    name: str
    icon_key: str | None
    monthly_limit: Decimal | None
    is_active: bool
    sort_order: int


class CategoryGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: CategoryType
    sort_order: int
    categories: list[CategoryRead]
