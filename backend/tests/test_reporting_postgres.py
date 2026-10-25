import os
from dataclasses import replace
from datetime import timedelta
from typing import cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_identity_postgres import headers
from test_orders_postgres import System
from test_orders_postgres import order_system as _order_system

from ashana.bootstrap.app import create_app
from ashana.bootstrap.pos import pos_service
from ashana.bootstrap.reporting import reporting_service
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.orders.domain.models import Choice
from ashana.modules.reporting.application.service import ReportingService
from ashana.modules.reporting.domain.models import ReportFilter
from ashana.modules.reporting.infrastructure.database import PostgresReportUnitOfWork
from ashana.shared.domain import BusinessError

Identity = tuple[Settings, IdentityService, str]

report_system = _order_system
pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


def setup_report(s: System, system: Identity) -> tuple[ReportingService, ReportFilter]:
    reports = reporting_service(s.engine, system[1])
    day = s.now.astimezone(ZoneInfo("Asia/Almaty")).date()
    return reports, ReportFilter(day, day)


def test_reports_sales_events_modes_channels_and_pagination(
    report_system: System, system: Identity
) -> None:
    s = report_system
    reports, filters = setup_report(s, system)
    entry, slot, _ = s.setup("20")
    with s.service.uow() as uow:
        card = uow.catalog.entry(entry)
        assert card is not None
    filters = replace(filters, item_id=card.item_id)
    guest = s.guest()
    unpaid = s.buy(guest, entry, slot)
    s.service.mock_payment(guest, unpaid.id, uuid4(), "failed")
    s.service.mock_payment(guest, unpaid.id, uuid4(), "timeout")
    before = reports.read(s.token, "sales", filters)
    assert before.total_rows == 0 and before.totals["paid_minor"] == "0"
    paid = s.service.mock_payment(guest, unpaid.id, uuid4(), "success")
    report = reports.read(s.token, "sales", filters)
    assert report.rows[0]["paid_quantity"] == "1" and report.rows[0]["issued_quantity"] == "0"
    ready = s.service.transition(s.token, paid.id, uuid4(), "preparing", paid.version)
    ready = s.service.transition(s.token, paid.id, uuid4(), "ready", ready.version)
    key = uuid4()
    for _ in range(2):
        s.service.transition(
            s.token, paid.id, key, "completed", ready.version, ready.pickup_code or ""
        )
    second = s.buy(guest, entry, slot, 2)
    s.service.mock_payment(guest, second.id, uuid4(), "success")
    with pytest.raises(BusinessError, match="нельзя отменить"):
        s.service.cancel(guest, second.id)
    pending_cancel = s.buy(guest, entry, slot)
    s.service.cancel(guest, pending_cancel.id)
    pos = pos_service(s.engine, system[1], s.service)
    pos.sell(s.token, uuid4(), [Choice(entry, 3, 12345)], "success")
    pos.sell(s.token, uuid4(), [Choice(entry, 1, 12345)], "failed")
    report = reports.read(s.token, "sales", filters, limit=1)
    assert report.total_rows == 2 and len(report.rows) == 1
    assert report.totals == {
        "paid_minor": str(6 * 12345),
        "issued_minor": str(4 * 12345),
        "refund_minor": "0",
    }
    assert report.unit_totals["pcs"]["issued_quantity"] == "4"
    page2 = reports.read(s.token, "sales", filters, offset=1, limit=1)
    assert page2.totals == report.totals and page2.rows != report.rows
    online = reports.read(
        s.token, "sales", replace(filters, channel="online", period_id=card.period_id)
    )
    assert online.rows[0]["cancelled_quantity"] == "1"
    assert online.totals["paid_minor"] == str(3 * 12345)
    assert reports.read(s.token, "sales", replace(filters, mode="real")).total_rows == 0
    assert reports.read(s.token, "sales", replace(filters, period_id=uuid4())).total_rows == 0


def test_reports_stock_units_writeoffs_and_count_are_distinct(
    report_system: System, system: Identity
) -> None:
    s = report_system
    reports, filters = setup_report(s, system)
    entry, slot, batch = s.setup("10")
    with s.service.uow() as uow:
        card = uow.catalog.entry(entry)
        assert card is not None
    filters = replace(filters, item_id=card.item_id)
    s.buy(s.guest(), entry, slot, 2)
    s.stock.change(s.token, uuid4(), batch, "write_off", "1", "pcs", "Демо списание", 2)
    s.stock.change(s.token, uuid4(), batch, "count", "8", "pcs", "Демо недостача", 3)
    s.stock.change(s.token, uuid4(), batch, "count", "9", "pcs", "Демо излишек", 4)
    s.stock.change(s.token, uuid4(), batch, "suspend", None, None, "Демо блокировка", 5)
    stock = reports.read(s.token, "stock", filters)
    row = stock.rows[0]
    assert float(row["on_hand"]) == 9 and float(row["reserved"]) == 2
    assert float(row["available"]) == 0 and float(row["blocked"]) == 7
    losses = reports.read(s.token, "writeoffs", filters)
    assert float(losses.rows[0]["written_off"]) == 1
    assert float(losses.rows[0]["count_loss"]) == float(losses.rows[0]["count_gain"]) == 1
    assert "production_consume" not in str(losses.rows)
    raw = s.stock.create_item(s.token, uuid4(), f"Мука отчёта {uuid4()}", "raw", "kg").subject_id
    s.stock.receive(
        s.token,
        uuid4(),
        raw,
        "Склад",
        "1.125",
        "kg",
        100,
        s.now - timedelta(hours=1),
        s.now + timedelta(days=1),
        "Демо",
    )
    all_stock = reports.read(s.token, "stock", replace(filters, item_id=None), limit=1)
    assert "kg" in all_stock.unit_totals and "pcs" in all_stock.unit_totals
    assert all_stock.total_rows > len(all_stock.rows)
    future = replace(
        filters, start=filters.start + timedelta(days=2), end=filters.end + timedelta(days=2)
    )
    assert reports.read(s.token, "stock", future).rows == stock.rows
    assert reports.read(s.token, "writeoffs", future).total_rows == 0


def test_reports_production_actual_output_not_sales(
    report_system: System, system: Identity
) -> None:
    from ashana.bootstrap.production import production_service
    from ashana.modules.production.domain.models import ConsumptionInput, IngredientInput

    s = report_system
    reports, filters = setup_report(s, system)
    raw = s.stock.create_item(s.token, uuid4(), f"Рис отчёта {uuid4()}", "raw", "kg").subject_id
    batch = s.stock.receive(
        s.token,
        uuid4(),
        raw,
        "Сырьё",
        "10",
        "kg",
        100,
        s.now - timedelta(hours=1),
        s.now + timedelta(days=1),
        "Демо",
    ).subject_id
    food = s.stock.create_item(
        s.token, uuid4(), f"Обед отчёта {uuid4()}", "prepared", "portion"
    ).subject_id
    production = production_service(s.engine, system[1])
    recipe = production.create_recipe(
        s.token, uuid4(), food, 0, 10, "250", "g", "Демо", [IngredientInput(raw, "2", "kg")]
    )
    for _ in range(2):
        production.produce(
            s.token,
            uuid4(),
            recipe.subject_id,
            "Партия",
            8,
            s.now + timedelta(days=1),
            True,
            [ConsumptionInput(batch, "2", "kg")],
        )
    report = reports.read(s.token, "production", replace(filters, item_id=food))
    assert report.rows[0]["quantity"] == "16" and report.rows[0]["batches"] == "2"
    assert reports.read(s.token, "writeoffs", replace(filters, item_id=raw)).total_rows == 0


def test_reports_almaty_day_boundary_uses_event_time(
    report_system: System, system: Identity
) -> None:
    s = report_system
    reports, filters = setup_report(s, system)
    entry, _, _ = s.setup("3")
    with s.service.uow() as uow:
        card = uow.catalog.entry(entry)
        assert card is not None
    filters = replace(filters, item_id=card.item_id)
    pos = pos_service(s.engine, system[1], s.service)
    sale = pos.sell(s.token, uuid4(), [Choice(entry, 1, 12345)], "success")
    # The reporting projection must obey an inclusive local day, regardless of server UTC date.
    start, end = filters.bounds()
    with s.engine.begin() as c:
        # Insert synthetic boundaries without editing immutable events.
        c.execute(
            text("""INSERT INTO pos_attempts
            (id,actor_id,outcome,mode,currency,total_minor,created_at,lines)
            SELECT :id,actor_id,outcome,mode,currency,total_minor,:created,lines
            FROM pos_attempts WHERE id=:source"""),
            {"id": uuid4(), "created": start, "source": sale.id},
        )
        c.execute(
            text("""INSERT INTO pos_attempts
            (id,actor_id,outcome,mode,currency,total_minor,created_at,lines)
            SELECT :id,actor_id,outcome,mode,currency,total_minor,:created,lines
            FROM pos_attempts WHERE id=:source"""),
            {"id": uuid4(), "created": end, "source": sale.id},
        )
    assert reports.read(s.token, "sales", filters).totals["paid_minor"] == str(2 * 12345)


def test_reports_auth_read_only_and_http_contract(report_system: System, system: Identity) -> None:
    s = report_system
    reports, filters = setup_report(s, system)
    identity, password = system[1:]
    staff = identity.create_staff(
        s.token, "Кассир", "report.cashier", password, frozenset({Role.CASHIER})
    )
    token = identity.login(staff.login, password, "report-tests")[1]
    with pytest.raises(IdentityError):
        reports.read(token, "stock", filters)
    with pytest.raises(IdentityError):
        reports.options(token, "items")
    with reports.uow() as uow:
        uow.authorize(s.token)
        with pytest.raises(DBAPIError):
            cast(PostgresReportUnitOfWork, uow).connection.execute(
                text("UPDATE inventory_items SET name=name WHERE false")
            )
    with TestClient(create_app(s.settings)) as client:
        path = f"/api/v1/reports/sales?start={filters.start}&end={filters.end}"
        assert client.get(path).status_code == 401
        client.cookies.set(s.settings.session_cookie, s.token)
        result = client.get(path)
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        assert not {"password", "pickup_code", "guest_id"} & result.json().keys()
        assert client.get(path + "&mode=all").status_code == 422
        assert client.get(path + "&limit=101").status_code == 422
        assert (
            client.post("/api/v1/reports/sales", json={}, headers=headers(client)).status_code
            == 405
        )
        assert client.get("/api/v1/reports/options/items").status_code == 200


def test_dashboard_atomic_totals_ranking_and_zero_sales(
    report_system: System, system: Identity
) -> None:
    s = report_system
    reports, filters = setup_report(s, system)
    entry, _, _ = s.setup("12")
    pos = pos_service(s.engine, system[1], s.service)
    before = reports.dashboard(s.token, filters)
    pos.sell(s.token, uuid4(), [Choice(entry, 8, 12345)], "success")
    after = reports.dashboard(s.token, filters)
    assert int(after.totals["paid_minor"]) - int(before.totals["paid_minor"]) == 8 * 12345
    assert len(after.top) <= 5 and len(after.low) <= 5
    assert [int(r["quantity"]) for r in after.top] == sorted(
        [int(r["quantity"]) for r in after.top], reverse=True
    )
    assert any(row["quantity"] == "0" for row in after.low)
    assert all("id" in row for row in after.top + after.low)
    with pytest.raises(IdentityError):
        reports.dashboard("", filters)
