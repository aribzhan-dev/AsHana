import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_identity_postgres import headers
from test_orders_postgres import System
from test_orders_postgres import order_system as _order_system

from ashana.bootstrap.app import create_app
from ashana.bootstrap.pos import pos_service
from ashana.bootstrap.reporting import reporting_service
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.inventory.domain.models import InvoiceLine
from ashana.modules.inventory.infrastructure.database import batches, items, movements
from ashana.modules.orders.domain.models import Choice
from ashana.modules.pos.application.service import PosService
from ashana.modules.reporting.domain.models import ReportFilter, ReportKind
from ashana.shared.domain import BusinessError

ops_system = _order_system
pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


Identity = tuple[Settings, IdentityService, str]


@pytest.fixture(scope="module")
def pos(ops_system: System, system: Identity) -> PosService:
    return pos_service(ops_system.engine, system[1], ops_system.service)


def on_hand(s: System, batch: UUID) -> Decimal:
    with s.engine.connect() as c:
        value: Decimal = c.execute(
            select(batches.c.on_hand).where(batches.c.id == batch)
        ).scalar_one()
        return value


def test_categories_are_one_shared_directory(ops_system: System) -> None:
    s = ops_system
    name = f"Напитки {uuid4().hex[:6]}"
    with pytest.raises(BusinessError, match="категорию"):
        s.stock.create_item(s.token, uuid4(), f"Сок {uuid4()}", "purchased", "pcs", category=name)
    s.stock.create_directory(s.token, uuid4(), "category", name)
    with pytest.raises(BusinessError, match="уже существует"):
        s.stock.create_directory(s.token, uuid4(), "category", name.upper())
    item = s.stock.create_item(
        s.token, uuid4(), f"Сок {uuid4()}", "purchased", "pcs", category=name.lower()
    ).subject_id
    with s.engine.connect() as c:
        assert c.execute(select(items.c.category).where(items.c.id == item)).scalar_one() == name
    with pytest.raises(BusinessError):
        s.stock.create_directory(s.token, uuid4(), "category", "К" * 61)


def test_always_on_menu_goods_join_open_periods_once(ops_system: System) -> None:
    s = ops_system
    with pytest.raises(BusinessError, match="Постоянно"):
        s.stock.create_item(s.token, uuid4(), f"Мука {uuid4()}", "raw", "kg", always_on_menu=True)
    with pytest.raises(BusinessError, match="Постоянно"):
        s.stock.create_item(
            s.token, uuid4(), f"Кола {uuid4()}", "purchased", "pcs", always_on_menu=True
        )
    cola = s.stock.create_item(
        s.token,
        uuid4(),
        f"Кола {uuid4()}",
        "purchased",
        "pcs",
        sale_price_minor=45000,
        always_on_menu=True,
    ).subject_id
    s.stock.receive(
        s.token,
        uuid4(),
        cola,
        "Поставка",
        "5",
        "pcs",
        100,
        s.now - timedelta(hours=1),
        s.now + timedelta(days=2),
        "Тест",
    )
    period = s.catalog.save_period(
        s.token,
        uuid4(),
        None,
        0,
        f"Период {uuid4()}",
        s.now - timedelta(minutes=30),
        s.now + timedelta(hours=3),
        True,
    ).subject_id
    first = [e for e in s.catalog.entries(s.token, period, 0, 100) if e.item_id == cola]
    assert len(first) == 1 and first[0].price_minor == 45000 and first[0].published
    key = uuid4()
    s.catalog.sync_permanent(s.token, key)
    s.catalog.sync_permanent(s.token, key)
    s.catalog.sync_permanent(s.token, uuid4())
    assert len([e for e in s.catalog.entries(s.token, period, 0, 100) if e.item_id == cola]) == 1
    found = []
    for offset in range(0, 10000, 100):
        _, page = s.catalog.menu(offset, 100)
        found += [e for e in page if e.id == first[0].id]
        if found or len(page) < 100:
            break
    assert found and found[0].available == 5
    # Undo the flag and hide synced entries so later tests' periods stay unchanged.
    with s.engine.connect() as c:
        name, version = c.execute(
            select(items.c.name, items.c.version).where(items.c.id == cola)
        ).one()
    s.stock.edit_item(s.token, uuid4(), cola, name, None, "", 0, 45000, version)
    with s.catalog.uow() as uow:
        open_periods = uow.repository.open_periods(s.now)
    for open_period in open_periods:
        for entry in s.catalog.entries(s.token, open_period.id, 0, 100):
            if entry.item_id == cola:
                s.catalog.save_entry(
                    s.token,
                    uuid4(),
                    open_period.id,
                    entry.id,
                    entry.version,
                    cola,
                    entry.description,
                    entry.portion_label,
                    entry.price_minor,
                    False,
                    entry.category,
                )


def test_dining_choice_is_saved_and_part_of_replay(ops_system: System) -> None:
    s = ops_system
    entry, slot, _ = s.setup()
    guest = s.guest()
    key = uuid4()
    order = s.service.checkout(guest, key, slot, [Choice(entry, 1, 12345)], "takeaway")
    assert order.dining == "takeaway"
    assert s.service.checkout(guest, key, slot, [Choice(entry, 1, 12345)], "takeaway") == order
    with pytest.raises(BusinessError, match="ключ"):
        s.service.checkout(guest, key, slot, [Choice(entry, 1, 12345)], "here")
    with pytest.raises(BusinessError, match="с собой"):
        s.service.checkout(guest, uuid4(), slot, [Choice(entry, 1, 12345)], "outside")
    paid = s.service.mock_payment(guest, order.id, uuid4(), "success")
    assert paid.dining == "takeaway"


def test_counter_return_restock_limits_replay_and_race(
    ops_system: System, pos: PosService, system: Identity
) -> None:
    s = ops_system
    entry, _, batch = s.setup("5")
    sale = pos.sell(s.token, uuid4(), [Choice(entry, 3, 12345)], "success")
    assert on_hand(s, batch) == 2
    key = uuid4()
    first = pos.return_sale(s.token, key, sale.id, {entry: 1}, "Гость передумал", "restock")
    assert pos.return_sale(s.token, key, sale.id, {entry: 1}, "Гость передумал", "restock") == first
    assert first.amount_minor == 12345 and on_hand(s, batch) == 3
    with s.engine.connect() as c:
        assert c.execute(
            select(movements.c.delta).where(
                movements.c.batch_id == batch, movements.c.action == "pos_return"
            )
        ).scalar_one() == Decimal(1)
    pos.return_sale(s.token, uuid4(), sale.id, {entry: 1}, "Пролили", "write_off")
    assert on_hand(s, batch) == 3
    # Returns exist only at the till and only for till sales: a paid site order is not one.
    online_entry, slot, _ = s.setup("5")
    guest = s.guest()
    online = s.service.mock_payment(guest, s.buy(guest, online_entry, slot).id, uuid4(), "success")
    with pytest.raises(BusinessError, match="продажа не найдена"):
        pos.return_sale(s.token, uuid4(), online.id, {online_entry: 1}, "С сайта", "restock")
    with pytest.raises(BusinessError, match="больше проданного"):
        pos.return_sale(s.token, uuid4(), sale.id, {entry: 2}, "Ещё", "write_off")

    def attempt(_: int) -> object:
        try:
            return pos.return_sale(s.token, uuid4(), sale.id, {entry: 1}, "Гонка", "restock")
        except BusinessError as e:
            return e.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert results.count("RETURN_LIMIT") == 1
    assert sum(r.amount_minor for r in pos.returns(s.token, sale.id)) == 3 * 12345
    assert pos.history(s.token, 0, 100)[0].returned_minor == 3 * 12345

    _, identity, password = system
    cashier = identity.create_staff(
        s.token, "Кассир", f"cash.{uuid4().hex[:8]}", password, frozenset({Role.CASHIER})
    )
    token = identity.login(cashier.login, password, "returns")[1]
    second = pos.sell(token, uuid4(), [Choice(entry, 1, 12345)], "success")
    with pytest.raises(IdentityError):
        pos.return_sale(token, uuid4(), second.id, {entry: 1}, "Нет права", "restock")
    with TestClient(create_app(s.settings)) as client:
        client.cookies.set(s.settings.session_cookie, s.token)
        body = {
            "lines": [{"entry_id": str(entry), "quantity": 1}],
            "reason": "HTTP",
            "disposition": "restock",
        }
        path = f"/api/v1/pos/sales/{second.id}/returns"
        assert (
            client.post(path, json=body, headers={"Idempotency-Key": str(uuid4())}).status_code
            == 403
        )
        response = client.post(
            path, json=body, headers={**headers(client), "Idempotency-Key": str(uuid4())}
        )
        assert response.status_code == 201 and response.json()["amount_minor"] == 12345


def test_supplier_debt_partial_payments_and_report(ops_system: System, system: Identity) -> None:
    s = ops_system
    supplier = s.stock.create_directory(
        s.token, uuid4(), "supplier", f"Поставщик {uuid4()}"
    ).subject_id
    cash = s.stock.create_directory(
        s.token, uuid4(), "payment_method", f"Касса {uuid4()}"
    ).subject_id
    rice = s.stock.create_item(s.token, uuid4(), f"Рис {uuid4()}", "raw", "kg").subject_id
    line = InvoiceLine(rice, "2", "kg", 50000, s.now + timedelta(days=3))
    warehouse = UUID("00000000-0000-0000-0000-000000000001")
    with pytest.raises(BusinessError, match="Оплачено"):
        s.stock.receive_invoice(
            s.token, uuid4(), str(uuid4()), supplier, warehouse, cash, s.now, 0, "", [line],
            paid_minor=100001,
        )  # fmt: skip
    invoice_id = s.stock.receive_invoice(
        s.token, uuid4(), str(uuid4()), supplier, warehouse, cash, s.now, 0, "", [line],
        paid_minor=40000,
    ).subject_id  # fmt: skip

    def pay(amount: int) -> object:
        try:
            return s.stock.pay_invoice(s.token, uuid4(), invoice_id, amount, cash, s.now)
        except BusinessError as e:
            return e.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(pay, [50000, 50000]))
    assert results.count("PAYMENT_EXCEEDS_DEBT") == 1
    invoice = next(i for i in s.stock.invoices(s.token, 0, 100) if i.id == invoice_id)
    assert (invoice.paid_minor, invoice.total_minor - invoice.paid_minor) == (90000, 10000)
    assert len(s.stock.invoice_payments(s.token, invoice_id)) == 1
    reports = reporting_service(s.engine, system[1])
    day = s.now.astimezone(ZoneInfo("Asia/Almaty")).date()
    debts = reports.read(s.token, "debts", ReportFilter(day, day), 0, 100)
    row = next(
        r for r in debts.rows if r["name"].startswith("Поставщик") and r["debt_minor"] == "10000"
    )
    assert row["paid_minor"] == "90000"
    assert pay(10000) != "PAYMENT_EXCEEDS_DEBT"
    debts = reports.read(s.token, "debts", ReportFilter(day, day), 0, 100)
    assert not any(r["name"] == row["name"] for r in debts.rows)


def test_new_reports_read_only_with_returns_and_abc(
    ops_system: System, pos: PosService, system: Identity
) -> None:
    s = ops_system
    reports = reporting_service(s.engine, system[1])
    day = s.now.astimezone(ZoneInfo("Asia/Almaty")).date()
    entry, _, _ = s.setup("10")
    sale = pos.sell(s.token, uuid4(), [Choice(entry, 4, 12345)], "success")
    pos.return_sale(s.token, uuid4(), sale.id, {entry: 1}, "Возврат", "write_off")
    with s.service.uow() as uow:
        card = uow.catalog.entry(entry)
    assert card is not None
    item = card.item_id
    filters = ReportFilter(day, day, item_id=item)
    returned = reports.read(s.token, "returns", filters, 0, 20)
    assert returned.rows[0]["quantity"] == "1" and returned.rows[0]["amount_minor"] == "12345"
    top = reports.read(s.token, "top", filters, 0, 20)
    assert top.rows[0]["quantity"] == "3" and top.rows[0]["revenue_minor"] == str(3 * 12345)
    abc = reports.read(s.token, "abc", filters, 0, 20)
    assert abc.rows[0]["grade"] == "A" and abc.rows[0]["cumulative"] == "100.0"
    kinds: tuple[ReportKind, ...] = (
        "unsold",
        "inventory",
        "expenses",
        "cashbook",
        "debts",
        "sales",
        "stock",
    )
    for kind in kinds:
        report = reports.read(s.token, kind, ReportFilter(day, day), 0, 20)
        assert report.kind == kind and report.note
    dashboard = reports.dashboard(s.token, ReportFilter(day, day))
    assert int(dashboard.totals["orders"]) >= 1 and dashboard.hours
