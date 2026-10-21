from uuid import uuid4

import pytest

from ashana.modules.inventory.domain.models import InventoryError
from ashana.modules.orders.domain.models import Choice, validate_choices


def test_cart_is_whole_bounded_and_unique() -> None:
    id = uuid4()
    validate_choices([Choice(id, 10, 12345)], 10)
    for choices in (
        [],
        [Choice(id, 0, 1)],
        [Choice(id, 11, 1)],
        [Choice(id, 1, 1), Choice(id, 1, 1)],
    ):
        with pytest.raises(InventoryError):
            validate_choices(choices, 10)
