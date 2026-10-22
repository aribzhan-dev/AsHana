import os
import secrets
from collections.abc import Iterator

import pytest

from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError
from ashana.modules.identity.infrastructure.database import PostgresIdentityUnitOfWork
from ashana.modules.identity.infrastructure.security import ArgonPasswords, KazakhstanMobilePhones


@pytest.fixture(scope="session")
def system() -> Iterator[tuple[Settings, IdentityService, str]]:
    settings = Settings()  # type: ignore[call-arg]
    engine = create_database_engine(settings)
    service = IdentityService(
        lambda: PostgresIdentityUnitOfWork(engine),
        ArgonPasswords(),
        KazakhstanMobilePhones(),
        allow_demo=True,
        ip_limit=500,
    )
    password = os.environ.get("ASHANA_TEST_PASSWORD") or secrets.token_urlsafe(24)
    service.bootstrap_admin("Әлия", "user01", password)
    yield settings, service, password
    engine.dispose()


_admin_token: list[str] = []


# Module scope: identity tests change the administrator's roles, which revokes older sessions.
# The token is reused while valid because logins per account are rate limited.
@pytest.fixture(scope="module")
def operations_admin(system: tuple[Settings, IdentityService, str]) -> str:
    _, identity, password = system
    if _admin_token:
        try:
            identity.authenticate(_admin_token[0])
            return _admin_token[0]
        except IdentityError:
            _admin_token.clear()
    _admin_token.append(identity.login("user01", password, "operations-tests")[1])
    return _admin_token[0]
