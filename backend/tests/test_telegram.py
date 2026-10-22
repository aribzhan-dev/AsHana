from uuid import UUID

from ashana.modules.orders.domain.models import short_number, tenge


def test_short_number_matches_the_guest_screen_and_money_is_readable() -> None:
    # Same rule as the web app: first 6 hex digits modulo 10000, four digits.
    order = UUID("cae50fe2-d7b7-475f-b584-b62333a2f68d")
    assert short_number(order) == f"{0xCAE50F % 10000:04d}"
    assert short_number(UUID(int=0)) == "0000"
    assert tenge(120000) == "1 200 ₸"
    assert tenge(12345) == "123,45 ₸"
