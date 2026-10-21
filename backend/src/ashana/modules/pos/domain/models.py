from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Sale:
    id: UUID
    actor_id: UUID
    outcome: str
    total_minor: int
    created_at: datetime
    lines: tuple["SaleLine", ...]
    payment_method_id: UUID | None = None
    payment_method_name: str = ""


@dataclass(frozen=True)
class SaleLine:
    entry_id: UUID
    item_id: UUID
    name: str
    portion_label: str
    unit: str
    quantity: int
    price_minor: int
