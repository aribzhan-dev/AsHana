import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4


class InventoryError(Exception):
    def __init__(self, code: str, message: str, field_errors: dict[str, list[str]] | None = None):
        super().__init__(message)
        self.code, self.message, self.field_errors = code, message, field_errors or {}


def invalid(field: str, message: str) -> InventoryError:
    return InventoryError("VALIDATION_ERROR", message, {field: [message]})


def text_value(value: str, field: str, maximum: int = 200) -> str:
    value = unicodedata.normalize("NFC", value.strip())
    if (
        not value
        or len(value) > maximum
        or any(unicodedata.category(c).startswith("C") for c in value)
    ):
        raise invalid(field, f"Введите текст от 1 до {maximum} символов без управляющих знаков")
    return value


def quantity(value: str, unit: str, base: str, *, allow_zero: bool = False) -> Decimal:
    factors = {
        "kg": ("kg", Decimal(1)),
        "g": ("kg", Decimal("0.001")),
        "l": ("l", Decimal(1)),
        "ml": ("l", Decimal("0.001")),
        "pcs": ("pcs", Decimal(1)),
        "portion": ("portion", Decimal(1)),
    }
    if unit not in factors or factors[unit][0] != base:
        raise invalid("unit", "Единица не соответствует позиции склада")
    if not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,3})?", value, flags=re.ASCII):
        raise invalid("quantity", "Введите число без экспоненты, до 3 знаков после точки")
    raw = Decimal(value)
    result = raw * factors[unit][1]
    if result < 0 or (result == 0 and not allow_zero) or result > Decimal("999999999"):
        raise invalid(
            "quantity",
            "Количество должно быть положительным и не превышать 999999999 базовых единиц",
        )
    if base in ("pcs", "portion") and raw != raw.to_integral_value():
        raise invalid("quantity", "Штуки и порции должны быть целыми")
    return result


@dataclass(frozen=True)
class Item:
    id: UUID
    name: str
    kind: str
    unit: str

    @classmethod
    def new(cls, name: str, kind: str, unit: str) -> "Item":
        allowed = {"raw": {"kg", "l"}, "purchased": {"pcs"}, "prepared": {"pcs", "portion"}}
        if kind not in allowed or unit not in allowed[kind]:
            raise invalid("unit", "Выберите единицу, подходящую типу позиции")
        return cls(uuid4(), text_value(name, "name", 100), kind, unit)


@dataclass(frozen=True)
class Batch:
    id: UUID
    item_id: UUID
    label: str
    on_hand: Decimal
    reserved: Decimal
    status: str
    version: int
    total_cost_minor: int
    received_at: datetime
    expires_at: datetime
    source: str
    actor_id: UUID
    created_at: datetime
    unit: str = "kg"
    item_name: str = ""
    item_kind: str = "raw"

    @property
    def free(self) -> Decimal:
        return self.on_hand - self.reserved

    def available_at(self, now: datetime) -> Decimal:
        return self.free if batch_state(self, now) == "active" else Decimal(0)


def batch_state(batch: Batch, now: datetime) -> str:
    if batch.status == "written_off":
        return "written_off"
    if batch.expires_at <= now:
        return "expired"
    if batch.status == "suspended":
        return "suspended"
    return "exhausted" if batch.on_hand == 0 else "active"


def change_quantity(batch: Batch, delta: Decimal) -> Batch:
    after = batch.on_hand + delta
    if after < batch.reserved:
        raise InventoryError(
            "INSUFFICIENT_STOCK", "Недостаточно свободного остатка: резерв нельзя списать"
        )
    if after > Decimal("999999999"):
        raise invalid("quantity", "Превышен предел количества партии")
    return replace(batch, on_hand=after, version=batch.version + 1)


@dataclass(frozen=True)
class Movement:
    id: UUID
    batch_id: UUID
    action: str
    delta: Decimal
    before: Decimal
    after: Decimal
    reason: str
    actor_id: UUID
    created_at: datetime
    version: int
    status_before: str
    status_after: str


@dataclass(frozen=True)
class Result:
    subject_id: UUID
    version: int
