import os
from concurrent.futures import ThreadPoolExecutor
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import select

from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError
from ashana.modules.identity.infrastructure.database import PostgresIdentityRepository, audit

Identity = tuple[Settings, IdentityService, str]

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)


# The shared administrator token: logins per account are rate limited for the whole run.
def test_custom_roles_permissions_revocation_audit_and_concurrent_edits(
    system: Identity, operations_admin: str
) -> None:
    _, identity, password = system
    token = operations_admin
    role = identity.save_role(token, "dispatch", "Выдача", frozenset({"kitchen.read"}), None)
    worker = identity.create_staff(token, "Айша", "dispatch.user", password, frozenset({role.code}))
    assert worker.effective_permissions == {"kitchen.read"}
    _, worker_token = identity.login(worker.login, password, "workspace-worker")
    identity.authenticate(worker_token).require("kitchen.read")
    with pytest.raises(IdentityError, match="Недостаточно прав"):
        identity.authenticate(worker_token).require("pos.sell")
    with pytest.raises(IdentityError, match="Недостаточно прав"):
        identity.save_role(
            worker_token, "forged", "Недопустимо", frozenset({"identity.manage"}), None
        )
    changed = identity.save_role(
        token, role.code, "Касса и выдача", frozenset({"pos.sell"}), role.version
    )
    with pytest.raises(IdentityError, match="Войдите"):
        identity.authenticate(worker_token)
    user, worker_token = identity.login(worker.login, password, "workspace-worker")
    assert user.effective_permissions == {"pos.sell"}
    identity.authenticate(worker_token).require("pos.sell")
    assert worker.id in {u.id for u in identity.list_staff(token)}
    with pytest.raises(IdentityError, match="существующие роли"):
        identity.assign_roles(token, worker.id, frozenset({"unknown"}))
    with pytest.raises(IdentityError):
        identity.save_role(token, "admin", "Администратор", frozenset(), 1)
    with pytest.raises(IdentityError):
        identity.save_role(token, "invalid", "Неверно", frozenset({"anything"}), None)

    def update(name: str) -> str:
        try:
            identity.save_role(token, changed.code, name, frozenset({"pos.sell"}), changed.version)
            return "ok"
        except IdentityError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(update, ["Касса первая", "Касса вторая"]))
    assert sorted(outcomes) == ["CONFLICT", "ok"]
    with identity.uow() as uow:
        rows = (
            cast(PostgresIdentityRepository, uow.repository)
            .connection.execute(select(audit.c.details).where(audit.c.action == "role_updated"))
            .scalars()
            .all()
        )
    assert any(r.get("role") == ["dispatch"] for r in rows)


def test_role_creation_conflict_is_not_overwrite(system: Identity, operations_admin: str) -> None:
    _, identity, _ = system
    token = operations_admin
    code = "role_" + uuid4().hex[:10]
    identity.save_role(token, code, "Роль", frozenset(), None)
    with pytest.raises(IdentityError, match="код занят"):
        identity.save_role(token, code, "Подмена", frozenset({"pos.sell"}), None)
