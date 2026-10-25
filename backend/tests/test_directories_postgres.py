import os
from uuid import UUID, uuid4

import pytest
from test_orders_postgres import System
from test_orders_postgres import order_system as _order_system

from ashana.bootstrap.pos import pos_service
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.orders.domain.models import Choice
from ashana.shared.domain import BusinessError

directory_system = _order_system
pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)
WAREHOUSE = UUID("00000000-0000-0000-0000-000000000001")
CARD = UUID("00000000-0000-0000-0000-000000000003")


def test_settings_entry_preview_rename_and_delete_only_when_unused(
    directory_system: System,
) -> None:
    s = directory_system
    tag = uuid4().hex[:6]
    supplier = s.stock.create_directory(s.token, uuid4(), "supplier", f"ТОО Тест {tag}").subject_id
    entry, usage = s.stock.directory(s.token, supplier)
    assert entry.name == f"ТОО Тест {tag}" and usage == {} and not entry.system
    key = uuid4()
    renamed = s.stock.rename_directory(s.token, key, supplier, f"ТОО Новый {tag}")
    assert s.stock.rename_directory(s.token, key, supplier, f"ТОО Новый {tag}") == renamed
    assert s.stock.directory(s.token, supplier)[0].name == f"ТОО Новый {tag}"
    other = s.stock.create_directory(s.token, uuid4(), "supplier", f"ТОО Другой {tag}").subject_id
    with pytest.raises(BusinessError, match="уже существует"):
        s.stock.rename_directory(s.token, uuid4(), other, f"ТОО Новый {tag}")
    s.stock.delete_directory(s.token, uuid4(), supplier)
    with pytest.raises(BusinessError, match="не найдена"):
        s.stock.directory(s.token, supplier)
    with pytest.raises(BusinessError, match="Системную"):
        s.stock.delete_directory(s.token, uuid4(), WAREHOUSE)
    assert s.stock.directory(s.token, WAREHOUSE)[1]["Партии на складе"] > 0


def test_category_rename_follows_goods_and_used_entries_are_kept(
    directory_system: System, system: tuple[Settings, IdentityService, str]
) -> None:
    s = directory_system
    tag = uuid4().hex[:6]
    category = s.stock.create_directory(s.token, uuid4(), "category", f"Тест {tag}").subject_id
    item = s.stock.create_item(
        s.token, uuid4(), f"Морс {tag}", "purchased", "pcs", category=f"Тест {tag}"
    ).subject_id
    assert s.stock.directory(s.token, category)[1] == {"Товары": 1}
    s.stock.rename_directory(s.token, uuid4(), category, f"Напитки {tag}")
    with s.stock.uow() as uow:
        renamed = uow.repository.item(item)
    assert renamed is not None and renamed.category == f"Напитки {tag}"
    with pytest.raises(BusinessError, match="используется"):
        s.stock.delete_directory(s.token, uuid4(), category)
    # A payment method used by a till sale stays: history keeps pointing to it.
    entry, _, _ = s.setup("5")
    pos_service(s.engine, system[1], s.service).sell(
        s.token, uuid4(), [Choice(entry, 1, 12345)], "success", CARD
    )
    assert s.stock.directory(s.token, CARD)[1]["Продажи на кассе"] > 0
    with pytest.raises(BusinessError, match="используется"):
        s.stock.delete_directory(s.token, uuid4(), CARD)
