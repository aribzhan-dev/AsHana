from decimal import Decimal

import pytest

from ashana.modules.production.domain.models import portion_size, whole_yield
from ashana.shared.domain import BusinessError


@pytest.mark.parametrize("value", [0, -1, True, 1.5, 1000000000])
def test_output_requires_positive_whole_count(value: int) -> None:
    with pytest.raises(BusinessError):
        whole_yield(value)


def test_portion_is_explicit_finished_mass_or_volume() -> None:
    assert whole_yield(12) == 12
    assert portion_size("250.125", "g") == (Decimal("0.250125"), "kg")
    assert portion_size("200", "ml") == (Decimal("0.2"), "l")
    with pytest.raises(BusinessError):
        portion_size("1", "portion")
