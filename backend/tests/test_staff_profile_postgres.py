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


def test_admin_edits_contacts_blocks_and_unblocks_staff(
    system: Identity, operations_admin: str
) -> None:
    _, identity, password = system
    login = f"profile.{uuid4().hex[:8]}"
    roles = frozenset({Role.CASHIER})
    user = identity.create_staff(
        operations_admin, "Кассир", login, password, roles, telegram="kassa_bot1"
    )
    assert user.telegram == "@kassa_bot1"
    updated = identity.update_profile(
        operations_admin, user.id, "Айгерим Касымова", "+77010000022", "@aigerim_k", "Айгерим"
    )
    seen = identity.staff_member(operations_admin, user.id)
    assert (
        (seen.name, seen.phone, seen.telegram, seen.nickname)
        == (
            "Айгерим Касымова",
            "+77010000022",
            "@aigerim_k",
            "Айгерим",
        )
        == (updated.name, updated.phone, updated.telegram, updated.nickname)
    )
    with pytest.raises(IdentityError) as bad:
        identity.update_profile(operations_admin, user.id, "Айгерим", None, "@ab", "")
    assert "telegram" in bad.value.field_errors
    # Contacts are optional: clearing them is allowed.
    cleared = identity.update_profile(operations_admin, user.id, "Айгерим", None, "", "")
    assert cleared.telegram is None and cleared.phone is None

    _, session = identity.login(login, password, "profile-before-block")
    assert not identity.set_active(operations_admin, user.id, False).is_active
    with pytest.raises(IdentityError):
        identity.authenticate(session)
    with pytest.raises(IdentityError):
        identity.login(login, password, "profile-blocked")
    assert identity.set_active(operations_admin, user.id, True).is_active
    identity.login(login, password, "profile-unblocked")

    me = identity.authenticate(operations_admin).user
    with pytest.raises(IdentityError, match="Свой доступ"):
        identity.set_active(operations_admin, me.id, False)
    with pytest.raises(IdentityError, match="Недостаточно прав"):
        identity.set_active(session_of(identity, login, password), me.id, False)


def session_of(identity: IdentityService, login: str, password: str) -> str:
    return identity.login(login, password, "profile-other")[1]


def test_deleted_staff_disappears_cannot_log_in_and_keeps_login(
    system: Identity, operations_admin: str
) -> None:
    _, identity, password = system
    login = f"leaver.{uuid4().hex[:8]}"
    user = identity.create_staff(
        operations_admin, "Повар", login, password, frozenset({Role.KITCHEN})
    )
    _, session = identity.login(login, password, "leaver")
    identity.delete_staff(operations_admin, user.id)
    identity.delete_staff(operations_admin, user.id)  # repeated delete is harmless
    assert user.id not in {u.id for u in identity.list_staff(operations_admin, 0, 100)}
    with pytest.raises(IdentityError, match="не найден"):
        identity.staff_member(operations_admin, user.id)
    with pytest.raises(IdentityError, match="не найден"):
        identity.find_staff(operations_admin, login)
    with pytest.raises(IdentityError):
        identity.authenticate(session)
    with pytest.raises(IdentityError):
        identity.login(login, password, "leaver-again")
    # History still points to this account, so its login is not handed to someone else.
    with pytest.raises(IdentityError, match="уже используется"):
        identity.create_staff(operations_admin, "Новый", login, password, frozenset({Role.KITCHEN}))
    me = identity.authenticate(operations_admin).user
    with pytest.raises(IdentityError, match="Свой доступ"):
        identity.delete_staff(operations_admin, me.id)
