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
    returned_minor: int = 0


@dataclass(frozen=True)
class SaleLine:
    entry_id: UUID
    item_id: UUID
    name: str
    portion_label: str
    unit: str
    quantity: int
    price_minor: int


@dataclass(frozen=True)
class SaleReturn:
    id: UUID
    sale_id: UUID
    actor_id: UUID
    created_at: datetime
    reason: str
    disposition: str
    amount_minor: int
    lines: tuple[SaleLine, ...]
