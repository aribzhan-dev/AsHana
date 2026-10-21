import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.inventory import inventory_service
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.inventory.domain.models import InventoryError

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


def test_product_profiles_and_author_names(system, operations_admin):
    settings, identity, password = system
    engine = create_database_engine(settings)
    service = inventory_service(engine, identity)
    token = operations_admin
    result = service.create_item(
        token, uuid4(), f"Вода {uuid4()}", "purchased", "pcs", None, "Вода", 10000, 20000
    )
    key = uuid4()
    args = (
        token,
        key,
        result.subject_id,
        f"Вода новая {uuid4()}",
        "4870000000099",
        "Напитки",
        12000,
        25000,
        1,
    )
    updated = service.edit_item(*args)
    assert updated.version == 2
    assert service.edit_item(*args) == updated
    with pytest.raises(InventoryError, match="изменился"):
        service.edit_item(token, uuid4(), result.subject_id, "Старый", None, "", 0, 0, 1)
    with pytest.raises(InventoryError):
        service.edit_item(token, uuid4(), result.subject_id, "Неверный", None, "", -1, 0, 2)
    now = datetime.now(UTC)
    receipt = service.receive(
        token,
        uuid4(),
        result.subject_id,
        "Поставка",
        "3",
        "pcs",
        36000,
        now,
        now + timedelta(days=2),
        "Поставщик",
    )
    principal = identity.authenticate(token)
    original = principal.user.nickname
    identity.set_nickname(token, principal.user.id, "Старший кассир", original)
    assert service.movements(token, receipt.subject_id, 0, 20)[0].actor_name == "Старший кассир"
    with pytest.raises(IdentityError, match="изменился"):
        identity.set_nickname(token, principal.user.id, "Другой", original)
    identity.set_nickname(token, principal.user.id, original, "Старший кассир")
    cashier = identity.create_staff(
        token,
        "Айша",
        f"p{uuid4().hex[:15]}",
        password,
        frozenset({Role.CASHIER}),
        nickname="Касса один",
    )
    _, cashier_token = identity.login(cashier.login, password, "profiles-test")
    with pytest.raises(IdentityError):
        service.edit_item(cashier_token, uuid4(), result.subject_id, "Запрещено", None, "", 0, 0, 2)
    with pytest.raises(IdentityError):
        identity.set_nickname(cashier_token, cashier.id, "Запрещено", "Касса один")
    engine.dispose()
