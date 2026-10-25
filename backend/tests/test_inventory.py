from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from ashana.modules.inventory.domain.models import (
    Batch,
    Item,
    batch_state,
    change_quantity,
    quantity,
)
from ashana.shared.domain import BusinessError


def test_explicit_conversion_and_integer_goods() -> None:
    assert quantity("1250.125", "g", "kg") == Decimal("1.250125")
    assert quantity("200", "ml", "l") == Decimal("0.2")
    assert quantity("2", "pcs", "pcs") == 2
    assert quantity("0", "kg", "kg", allow_zero=True) == 0


@pytest.mark.parametrize(
    "value,unit,base",
    [
        ("1e3", "kg", "kg"),
        ("NaN", "kg", "kg"),
        ("Infinity", "kg", "kg"),
        ("-1", "kg", "kg"),
        ("0", "kg", "kg"),
        ("1.0001", "g", "kg"),
        ("1", "kg", "l"),
        ("1.5", "pcs", "pcs"),
        ("1000000000", "kg", "kg"),
        ("1,2", "kg", "kg"),
        ("１２", "kg", "kg"),
    ],
)
def test_invalid_quantities(value: str, unit: str, base: str) -> None:
    with pytest.raises(BusinessError):
        quantity(value, unit, base)


def test_adjustment_preserves_reservations_and_expiry() -> None:
    now = datetime.now(UTC)
    batch = Batch(
        uuid4(),
        uuid4(),
        "Партия",
        Decimal("8"),
        Decimal("3"),
        "active",
        1,
        100,
        now - timedelta(hours=1),
        now + timedelta(hours=1),
        "Источник",
        uuid4(),
        now,
    )
    assert batch.free == 5 and batch.available_at(now) == 5
    assert replace(batch, status="suspended").available_at(now) == 0
    assert batch.available_at(now + timedelta(hours=2)) == 0
    assert batch_state(batch, now) == "active"
    assert change_quantity(batch, Decimal("-5")).on_hand == 3
    with pytest.raises(BusinessError):
        change_quantity(batch, Decimal("-6"))
    assert batch_state(batch, now + timedelta(hours=2)) == "expired"


def test_item_types_require_compatible_unit() -> None:
    assert Item.new("Рис", "raw", "kg").unit == "kg"
    with pytest.raises(BusinessError):
        Item.new("Рис", "raw", "pcs")
    with pytest.raises(BusinessError):
        Item.new("Сок", "purchased", "l")
