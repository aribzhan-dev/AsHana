from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ashana.modules.inventory.domain.models import invalid


@dataclass(frozen=True)
class OrderPolicy:
    max_active: int = 2
    max_portions: int = 10
    reservation_seconds: int = 300
    cutoff_minutes: int = 15
    slot_minutes: int = 10
    slot_capacity: int = 10
    # A paid order nobody picked up this long after its slot becomes "no_show".
    pickup_grace_minutes: int = 60


@dataclass(frozen=True)
class Slot:
    id: UUID
    period_id: UUID
    starts_at: datetime
    ends_at: datetime
    cutoff_at: datetime
    capacity: int
    occupied: int
    enabled: bool
    version: int


@dataclass(frozen=True)
class Choice:
    entry_id: UUID
    quantity: int
    expected_price_minor: int


def validate_choices(choices: list[Choice], maximum: int) -> None:
    if not choices or len(choices) > maximum:
        raise invalid("lines", f"Выберите от 1 до {maximum} позиций")
    if len({c.entry_id for c in choices}) != len(choices):
        raise invalid("lines", "Объедините одинаковые позиции")
    if any(type(c.quantity) is not int or c.quantity < 1 for c in choices):
        raise invalid("lines", "Количество порций должно быть целым и положительным")
    if sum(c.quantity for c in choices) > maximum:
        raise invalid("lines", f"В одном заказе не более {maximum} порций / штук")


@dataclass(frozen=True)
class OrderLine:
    entry_id: UUID
    item_id: UUID
    name: str
    portion_label: str
    unit: str
    quantity: int
    price_minor: int


@dataclass(frozen=True)
class Order:
    id: UUID
    guest_id: UUID
    slot_id: UUID
    status: str
    total_minor: int
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    version: int
    lines: tuple[OrderLine, ...]
    slot_starts_at: datetime
    slot_ends_at: datetime
    stock_issue: bool = False
    pickup_code: str | None = None
    dining: str = "here"


def short_number(order_id: UUID) -> str:
    """Display number shown to guests and staff; not unique and never used for lookup."""
    return f"{int(order_id.hex[:6], 16) % 10000:04d}"


def tenge(minor: int) -> str:
    whole = f"{minor // 100:,}".replace(",", "\u00a0")
    return f"{whole} ₸" if minor % 100 == 0 else f"{whole},{minor % 100:02d} ₸"
