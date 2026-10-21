from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from ashana.modules.catalog.domain.models import Period, meal_date, price_minor, validate_period
from ashana.modules.inventory.domain.models import InventoryError


def test_period_boundaries_and_almaty_date() -> None:
    start = datetime(2026, 10, 21, 19, tzinfo=UTC)
    assert meal_date(start).isoformat() == "2026-10-22"
    period = Period(
        uuid4(), "Завтрак", start, start + timedelta(hours=2), True, 1, uuid4(), start, start
    )
    assert not period.active_at(start - timedelta(microseconds=1))
    assert period.active_at(start)
    assert not period.active_at(period.ends_at)
    validate_period(start, start + timedelta(days=1))
    maximum = datetime.max.replace(tzinfo=UTC)
    validate_period(maximum - timedelta(hours=1), maximum)
    for end in (start, start - timedelta(seconds=1), start + timedelta(days=1, seconds=1)):
        with pytest.raises(InventoryError):
            validate_period(start, end)
    with pytest.raises(InventoryError):
        validate_period(start.replace(tzinfo=None), period.ends_at)


@pytest.mark.parametrize("value", [-1, True, 1.5, 1000000000000])
def test_price_is_bounded_integer_tiyn(value: int) -> None:
    with pytest.raises(InventoryError):
        price_minor(value)


def test_zero_price_is_explicitly_allowed() -> None:
    assert price_minor(0) == 0
    assert price_minor(12345) == 12345
