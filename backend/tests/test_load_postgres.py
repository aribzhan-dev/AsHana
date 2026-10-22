import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_orders_postgres import System
from test_orders_postgres import order_system as _order_system

from ashana.bootstrap.pos import pos_service
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.inventory.domain.models import InventoryError
from ashana.modules.inventory.infrastructure.database import batches
from ashana.modules.orders.domain.models import Choice, Order
from ashana.modules.pos.domain.models import Sale

load_system = _order_system
pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


def stock(s: System, batch: object) -> tuple[int, int]:
    with s.engine.connect() as c:
        row = c.execute(
            select(batches.c.on_hand, batches.c.reserved).where(batches.c.id == batch)
        ).one()
        return int(row.on_hand), int(row.reserved)


def test_lunch_rush_never_oversells_last_portions(load_system: System) -> None:
    """40 students race for 15 portions in one slot: exactly 15 reservations succeed."""
    s = load_system
    entry, slot, batch = s.setup("15", 40)
    guests = [s.guest() for _ in range(40)]

    def order(guest: str) -> object:
        try:
            return s.buy(guest, entry, slot)
        except InventoryError as e:
            return e.code

    started = time.monotonic()
    with ThreadPoolExecutor(20) as pool:
        results = list(pool.map(order, guests))
    elapsed = time.monotonic() - started
    won = [r for r in results if isinstance(r, Order)]
    assert len(won) == 15
    assert set(results) - {*won} == {"INSUFFICIENT_STOCK"}
    on_hand, reserved = stock(s, batch)
    assert (on_hand, reserved) == (15, 15)
    # A generous bound: the point is that locking does not serialise into minutes.
    assert elapsed < 60, f"40 оформлений заняли {elapsed:.1f} с"


def test_counter_and_site_share_stock_under_load(
    load_system: System, system: tuple[Settings, IdentityService, str]
) -> None:
    """20 till sales and 20 online checkouts compete for 10 pieces: no more than 10 leave."""
    s = load_system
    pos = pos_service(s.engine, system[1], s.service)
    entry, slot, batch = s.setup("10", 40)
    guests = [s.guest() for _ in range(20)]

    def attempt(n: int) -> object:
        try:
            if n % 2:
                return pos.sell(s.token, uuid4(), [Choice(entry, 1, 12345)], "success")
            return s.buy(guests[n // 2], entry, slot)
        except InventoryError as e:
            return e.code

    with ThreadPoolExecutor(16) as pool:
        results = list(pool.map(attempt, range(40)))
    sold = sum(isinstance(r, Sale) for r in results)
    reserved_orders = sum(isinstance(r, Order) for r in results)
    assert sold + reserved_orders == 10
    on_hand, reserved = stock(s, batch)
    assert on_hand == 10 - sold and reserved == reserved_orders
    with s.engine.connect() as c:
        negative = c.execute(
            select(func.count()).select_from(batches).where(batches.c.on_hand < batches.c.reserved)
        ).scalar_one()
    assert negative == 0
