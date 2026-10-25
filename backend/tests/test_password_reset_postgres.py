import os
from uuid import uuid4

import pytest

from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError, Role

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)
Identity = tuple[Settings, IdentityService, str]


def test_admin_resets_forgotten_staff_password(system: Identity, operations_admin: str) -> None:
    _, identity, password = system
    login = f"forgot.{uuid4().hex[:8]}"
    user = identity.create_staff(
        operations_admin, "Кассир", login, password, frozenset({Role.CASHIER})
    )
    _, old_session = identity.login(login, password, "reset-old")
    new = "Новый-пароль-2026"
    identity.reset_password(operations_admin, user.id, new)
    # The old session and the old password stop working at once.
    with pytest.raises(IdentityError):
        identity.authenticate(old_session)
    with pytest.raises(IdentityError):
        identity.login(login, password, "reset-wrong")
    _, session = identity.login(login, new, "reset-new")
    assert identity.authenticate(session).user.id == user.id
    with pytest.raises(IdentityError, match="Недостаточно прав"):
        identity.reset_password(session, user.id, "Чужой-пароль-2026")
    with pytest.raises(IdentityError, match="Свой пароль"):
        admin = identity.authenticate(operations_admin).user
        identity.reset_password(operations_admin, admin.id, "Свой-пароль-2026")
    with pytest.raises(IdentityError):
        identity.reset_password(operations_admin, user.id, "abc")


def test_server_command_recovers_administrator_password(
    system: Identity, operations_admin: str
) -> None:
    _, identity, password = system
    login = f"admin.{uuid4().hex[:8]}"
    admin = identity.create_staff(
        operations_admin, "Второй админ", login, password, frozenset({Role.ADMIN})
    )
    try:
        identity.recover_admin(login, "Восстановлен-2026")
        _, session = identity.login(login, "Восстановлен-2026", "recovered")
        assert Role.ADMIN in identity.authenticate(session).user.roles
        with pytest.raises(IdentityError, match="не найден"):
            identity.recover_admin("nobody.here", "Восстановлен-2026")
        with pytest.raises(IdentityError, match="локальном"):
            production = IdentityService(
                identity.uow, identity.passwords, identity.phones, allow_demo=False
            )
            production.recover_admin(login, "Восстановлен-2026")
    finally:
        # Keep a single administrator for the browser tests that follow.
        identity.assign_roles(operations_admin, admin.id, frozenset({Role.MANAGER}))
