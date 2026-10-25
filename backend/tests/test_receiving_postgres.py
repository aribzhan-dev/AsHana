import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.inventory import inventory_service
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.inventory.domain.models import InvoiceLine
from ashana.modules.inventory.infrastructure.database import batches, invoices, movements
from ashana.shared.domain import BusinessError, Result

Identity = tuple[Settings, IdentityService, str]

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


def test_invoice_atomicity_replay_totals_permissions(
    system: Identity, operations_admin: str
) -> None:
    settings, identity, password = system
    engine = create_database_engine(settings)
    service = inventory_service(engine, identity)
    token = operations_admin
    now = datetime.now(UTC)
    supplier = service.create_directory(
        token, uuid4(), "supplier", f"Поставщик {uuid4()}"
    ).subject_id
    warehouse = service.create_directory(token, uuid4(), "warehouse", f"Склад {uuid4()}").subject_id
    method = service.create_directory(
        token, uuid4(), "payment_method", f"Перевод {uuid4()}"
    ).subject_id
    rice = service.create_item(token, uuid4(), f"Крупа {uuid4()}", "raw", "kg").subject_id
    water = service.create_item(
        token, uuid4(), f"Вода {uuid4()}", "purchased", "pcs", "4870000000001"
    ).subject_id
    lines = [
        InvoiceLine(rice, "1.255", "kg", 101, now + timedelta(days=3)),
        InvoiceLine(water, "4", "pcs", 12000, now + timedelta(days=2)),
    ]
    key, number = uuid4(), str(uuid4())

    def receive(ls: list[InvoiceLine] = lines, k: UUID = key, n: str = number) -> Result:
        return service.receive_invoice(
            token, k, n, supplier, warehouse, method, now, 5000, "Доставка", ls
        )

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: receive(), range(2)))
    assert results[0] == results[1]
    invoice = next(i for i in service.invoices(token, 0, 100) if i.id == results[0].subject_id)
    assert invoice.goods_minor == 48127 and invoice.total_minor == 53127
    assert invoice.warehouse_name.startswith("Склад") and len(invoice.lines) == 2
    with engine.connect() as c:
        assert (
            c.execute(
                select(func.count()).select_from(batches).where(batches.c.label == number)
            ).scalar_one()
            == 2
        )
        for line in invoice.lines:
            assert (
                c.execute(
                    select(func.count())
                    .select_from(movements)
                    .where(movements.c.batch_id == UUID(str(line["batch_id"])))
                ).scalar_one()
                == 1
            )
    with pytest.raises(BusinessError, match="ключ"):
        receive(lines[:1])
    with pytest.raises(BusinessError, match="уже проведена"):
        receive(k=uuid4())
    invalid_number = str(uuid4())
    with pytest.raises(BusinessError):
        receive(
            [lines[0], InvoiceLine(water, "0", "pcs", 10, now + timedelta(days=1))],
            uuid4(),
            invalid_number,
        )
    with engine.connect() as c:
        assert (
            c.execute(
                select(func.count()).select_from(batches).where(batches.c.label == invalid_number)
            ).scalar_one()
            == 0
        )
    with pytest.raises(BusinessError):
        service.create_item(
            token, uuid4(), f"Дубликат {uuid4()}", "purchased", "pcs", "4870000000001"
        )
    with pytest.raises(BusinessError):
        service.create_item(token, uuid4(), "Неверный код", "purchased", "pcs", "abcdefgh")
    with pytest.raises(BusinessError):
        service.create_item(token, uuid4(), "Сырьё с кодом", "raw", "kg", "4870000000002")
    barcode_key = uuid4()
    service.set_barcode(token, barcode_key, water, "4870000000002", "4870000000001")
    service.set_barcode(token, barcode_key, water, "4870000000002", "4870000000001")
    with pytest.raises(BusinessError, match="изменился"):
        service.set_barcode(token, uuid4(), water, "4870000000003", "4870000000001")
    assert all(b.warehouse_id == warehouse for b in service.batches(token, 0, 100, warehouse))
    assert not service.batches(token, 0, 100, warehouse, "Несуществующий товар")
    identity.create_staff(token, "Кассир", "receiving.cashier", password, frozenset({Role.CASHIER}))
    cashier = identity.login("receiving.cashier", password, "receiving-test")[1]
    with pytest.raises(IdentityError):
        service.receive_invoice(
            cashier, uuid4(), "Запрещено", supplier, warehouse, method, now, 0, "", lines
        )
    cash = inventory_service(engine, identity, cashier=True)
    with pytest.raises(BusinessError):
        cash.change(
            cashier,
            uuid4(),
            UUID(str(invoice.lines[0]["batch_id"])),
            "write_off",
            "1",
            "kg",
            "Сырьё",
            1,
        )
    bid = UUID(str(invoice.lines[1]["batch_id"]))
    with pytest.raises(BusinessError):
        cash.change(cashier, uuid4(), bid, "count", "3", "pcs", "Пересчёт запрещён", 1)
    cash.change(cashier, uuid4(), bid, "write_off", "1", "pcs", "Не продано", 1)
    assert all(b.item_kind != "raw" for b in cash.batches(cashier, 0, 100))
    with engine.begin() as c, pytest.raises(DBAPIError):
        c.execute(
            invoices.update()
            .where(invoices.c.id == invoice.id)
            .values(note="Нельзя менять историю")
        )
    engine.dispose()
