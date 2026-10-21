from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ashana.modules.inventory.domain.models import invalid, quantity


def whole_yield(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 999999999:
        raise invalid("yield_quantity", "Введите целый выход от 1 до 999999999")
    return value


def portion_size(value: str, unit: str) -> tuple[Decimal, str]:
    base = {"kg": "kg", "g": "kg", "l": "l", "ml": "l"}.get(unit)
    if base is None:
        raise invalid("portion_unit", "Укажите массу или объём одной готовой порции")
    return quantity(value, unit, base), base


@dataclass(frozen=True)
class IngredientInput:
    item_id: UUID
    quantity: str
    unit: str


@dataclass(frozen=True)
class ConsumptionInput:
    batch_id: UUID
    quantity: str
    unit: str


@dataclass(frozen=True)
class RecipeLine:
    item_id: UUID
    quantity: Decimal
    unit: str
    item_name: str = ""


@dataclass(frozen=True)
class Recipe:
    id: UUID
    output_item_id: UUID
    version: int
    expected_yield: int
    portion_quantity: Decimal
    portion_unit: str
    instructions: str
    actor_id: UUID
    created_at: datetime
    lines: tuple[RecipeLine, ...]
    output_name: str = ""
    output_unit: str = "portion"


@dataclass(frozen=True)
class Consumption:
    batch_id: UUID
    quantity: Decimal
    unit: str
    movement_id: UUID
    item_id: UUID
    item_name: str = ""
    batch_label: str = ""


@dataclass(frozen=True)
class Production:
    id: UUID
    recipe_id: UUID
    actual_yield: int
    actor_id: UUID
    created_at: datetime
    consumption: tuple[Consumption, ...]
    label: str = ""
    output_name: str = ""
    output_unit: str = "portion"
    recipe_version: int = 1
    expires_at: datetime | None = None
