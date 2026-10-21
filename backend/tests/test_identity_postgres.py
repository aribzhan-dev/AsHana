import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from ashana.bootstrap.app import create_app
from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService, token_digest
from ashana.modules.identity.domain.models import IdentityError, Role
from ashana.modules.identity.infrastructure.database import (
    audit,
    sessions,
    users,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("ASHANA_RUN_INTEGRATION") != "1", reason="Нужен изолированный PostgreSQL"
)
ORIGIN = "http://127.0.0.1:18081"


def headers(client: TestClient) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}


def test_http_auth_ownership_csrf_and_roles(system: tuple[Settings, IdentityService, str]) -> None:
    settings, service, password = system
    with TestClient(create_app(settings)) as admin, TestClient(create_app(settings)) as worker:
        assert admin.get("/api/v1/auth/me").status_code == 401
        assert admin.post("/api/v1/auth/register", json={}).status_code == 404
        data = {"login": "user01", "password": password}
        assert admin.post("/api/v1/auth/login", json=data).status_code == 403
        bad = {**headers(admin), "Origin": "https://example.invalid"}
        assert admin.post("/api/v1/auth/login", json=data, headers=bad).status_code == 403
        login = admin.post("/api/v1/auth/login", json=data, headers=headers(admin))
        assert login.status_code == 200, login.text
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "SameSite=lax" in login.headers["set-cookie"]
        assert login.headers["cache-control"] == "no-store"
        assert "password" not in login.text and "token" not in login.text
        admin_id = login.json()["id"]
        raw_token = admin.cookies.get(settings.session_cookie)
        assert raw_token
        with service.uow() as uow:
            stored = uow.repository.session_for_token(token_digest(raw_token))
            assert stored and stored.token_hash != raw_token
        payload = {
            "login": "user02",
            "password": password,
            "name": "Нұрлан",
            "roles": ["kitchen"],
        }
        created = admin.post("/api/v1/admin/users", json=payload, headers=headers(admin))
        assert created.status_code == 201, created.text
        worker_id = created.json()["id"]
        assert (
            admin.post("/api/v1/admin/users", json=payload, headers=headers(admin)).status_code
            == 409
        )
        forged = worker.post(
            "/api/v1/auth/login", json={**data, "roles": ["admin"]}, headers=headers(worker)
        )
        assert forged.status_code == 422 and password not in forged.text
        assert (
            worker.post(
                "/api/v1/auth/login",
                json={"login": payload["login"], "password": password},
                headers=headers(worker),
            ).status_code
            == 200
        )
        assert (
            worker.post("/api/v1/admin/users", json=payload, headers=headers(worker)).status_code
            == 403
        )
        own_sessions = worker.get("/api/v1/auth/sessions").json()
        foreign_id = admin.get("/api/v1/auth/sessions").json()[0]["id"]
        assert (
            worker.delete(
                f"/api/v1/auth/sessions/{foreign_id}", headers=headers(worker)
            ).status_code
            == 404
        )
        assert (
            admin.put(
                f"/api/v1/admin/users/{admin_id}/roles",
                json={"roles": ["manager"]},
                headers=headers(admin),
            ).json()["code"]
            == "LAST_ADMIN"
        )
        assert (
            admin.put(
                f"/api/v1/admin/users/{worker_id}/roles",
                json={"roles": ["cashier"]},
                headers=headers(admin),
            ).status_code
            == 200
        )
        assert worker.get("/api/v1/auth/me").status_code == 401
        assert service.authenticate(raw_token).user.id == UUID(admin_id)
        assert own_sessions[0]["current"]
        assert admin.post("/api/v1/auth/logout", headers=headers(admin)).status_code == 204
        admin.cookies.set(settings.session_cookie, raw_token)
        assert admin.get("/api/v1/auth/me").status_code == 401
        assert admin.post("/api/v1/auth/logout", headers=headers(admin)).status_code == 204


def test_transactions_concurrency_expiry_and_rate(
    system: tuple[Settings, IdentityService, str],
) -> None:
    settings, service, password = system
    _, admin_token = service.login("user01", password, "integration-admin")

    def create_once() -> str:
        try:
            service.create_staff(
                admin_token, "Аслан", "user03", password, frozenset({Role.CASHIER})
            )
            return "created"
        except IdentityError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: create_once(), range(2))) == ["USER_EXISTS", "created"]
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(func.count()).select_from(users).where(users.c.login == "user03")
                ).scalar_one()
                == 1
            )
        target = service.find_staff(admin_token, "user03")
        with pytest.raises(RuntimeError), service.uow() as uow:
            uow.repository.update_roles(target.id, frozenset({Role.ADMIN}))
            uow.repository.audit("rollback_probe", target.id, target.id, datetime.now(UTC), {})
            raise RuntimeError("rollback")
        assert service.find_staff(admin_token, target.login).roles == {Role.CASHIER}
        with engine.connect() as connection:
            assert (
                connection.execute(
                    select(func.count())
                    .select_from(audit)
                    .where(audit.c.action == "rollback_probe")
                ).scalar_one()
                == 0
            )
        # Runtime cannot rewrite the audit trail, even with direct SQL access.
        with engine.begin() as connection, pytest.raises(DBAPIError):
            connection.execute(
                audit.update().where(audit.c.action == "nonexistent").values(action="changed")
            )
        _, first = service.login(target.login, password, "integration-worker")
        _, second = service.login(target.login, password, "integration-worker", first)
        with pytest.raises(IdentityError, match="Войдите"):
            service.authenticate(first)
        expiring = IdentityService(
            service.uow,
            service.passwords,
            service.phones,
            allow_demo=True,
            clock=lambda: datetime.now(UTC) + timedelta(hours=13),
        )
        with pytest.raises(IdentityError, match="Войдите"):
            expiring.authenticate(second)
        production = IdentityService(
            service.uow, service.passwords, service.phones, allow_demo=False
        )
        with pytest.raises(IdentityError):
            production.authenticate(second)
        limited = IdentityService(
            service.uow, service.passwords, service.phones, allow_demo=True, login_limit=2
        )
        for _ in range(2):
            with pytest.raises(IdentityError) as invalid:
                limited.login("user04", password, "rate-probe")
            assert invalid.value.code == "INVALID_CREDENTIALS"
        restarted = IdentityService(
            service.uow, service.passwords, service.phones, allow_demo=True, login_limit=2
        )
        with pytest.raises(IdentityError) as limited_error:
            restarted.login("user04", password, "rate-probe")
        assert limited_error.value.code == "RATE_LIMITED"
        with engine.connect() as connection:
            hashes = connection.execute(select(sessions.c.token_hash)).scalars().all()
            assert first not in hashes and second not in hashes
    finally:
        engine.dispose()


def test_last_admin_under_concurrent_changes(system: tuple[Settings, IdentityService, str]) -> None:
    _, service, password = system
    _, token = service.login("user01", password, "admin-race")
    first = service.authenticate(token).user
    second = service.create_staff(
        token, "Администратор", "user05", password, frozenset({Role.ADMIN})
    )
    _, other_token = service.login(second.login, password, "admin-race-other")

    def demote(pair: tuple[str, UUID]) -> str:
        try:
            service.assign_roles(pair[0], pair[1], frozenset({Role.MANAGER}))
            return "changed"
        except IdentityError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(demote, [(token, second.id), (other_token, first.id)]))
    assert results.count("changed") == 1
    assert set(results) <= {"changed", "UNAUTHENTICATED", "FORBIDDEN", "LAST_ADMIN"}
    with service.uow() as uow:
        assert uow.repository.admin_count() == 1
        survivor = uow.repository.user_by_id(first.id)
    # Restore the fixture administrator for browser tests through the surviving administrator.
    if survivor and Role.ADMIN not in survivor.roles:
        _, surviving_token = service.login(second.login, password, "admin-restore")
        service.assign_roles(surviving_token, first.id, frozenset({Role.ADMIN, Role.MANAGER}))
    else:
        service.assign_roles(token, first.id, frozenset({Role.ADMIN, Role.MANAGER}))


def test_secure_cookie_own_revocation_and_uniform_errors(
    system: tuple[Settings, IdentityService, str],
) -> None:
    settings, service, password = system
    _, admin_token = service.login("user01", password, "secure-test-admin")
    service.create_staff(admin_token, "Айдана", "user06", password, frozenset({Role.MANAGER}))
    secured = settings.model_copy(
        update={
            "cookie_secure": True,
            "allowed_origins": ["https://testserver"],
        }
    )
    with TestClient(create_app(secured), base_url="https://testserver") as client:

        def secure_headers() -> dict[str, str]:
            return {
                "Origin": "https://testserver",
                "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"],
            }

        errors = []
        for login in ("user06", "user07", "invalid+login"):
            result = client.post(
                "/api/v1/auth/login",
                headers=secure_headers(),
                json={
                    "login": login,
                    "password": "invalid-placeholder",
                },
            )
            assert result.status_code == 401
            errors.append((result.json()["code"], result.json()["message"]))
        assert len(set(errors)) == 1
        before_login = secure_headers()
        response = client.post(
            "/api/v1/auth/login",
            headers=before_login,
            json={
                "login": "user06",
                "password": password,
            },
        )
        assert response.status_code == 200
        assert "__Host-ashana_session=" in response.headers["set-cookie"]
        assert "Secure" in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "Domain=" not in response.headers["set-cookie"]
        assert client.post("/api/v1/auth/logout", headers=before_login).status_code == 403
        assert (
            client.post(
                "/api/v1/auth/logout",
                headers={
                    **secure_headers(),
                    "Sec-Fetch-Site": "cross-site",
                },
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/admin/users/search",
                headers=secure_headers(),
                json={
                    "login": "user01",
                },
            ).status_code
            == 403
        )
        current = client.get("/api/v1/auth/sessions").json()[0]
        raw = client.cookies.get(secured.session_cookie)
        assert raw
        assert (
            client.delete(
                f"/api/v1/auth/sessions/{current['id']}",
                headers=secure_headers(),
            ).status_code
            == 204
        )
        assert not client.cookies.get(secured.session_cookie)
        with pytest.raises(IdentityError):
            service.authenticate(raw)


def test_contact_is_optional_and_not_an_auth_identifier(
    system: tuple[Settings, IdentityService, str],
) -> None:
    settings, service, password = system
    _, token = service.login(" USER01 ", password, "contact-test-admin")
    first = service.create_staff(
        token,
        "Айша",
        "Contact.One",
        password,
        frozenset({Role.KITCHEN}),
        phone="+7 (701) 000-00-11",
    )
    second = service.create_staff(
        token, "Арман", "contact.two", password, frozenset({Role.KITCHEN}), phone="+77010000011"
    )
    assert first.login == "contact.one" and first.phone == second.phone
    assert service.login("CONTACT.ONE", password, "contact-test-worker")[0].id == first.id
    with pytest.raises(IdentityError) as phone_login:
        service.login(first.phone or "", password, "contact-test-phone")
    assert phone_login.value.code == "INVALID_CREDENTIALS"
    with pytest.raises(IdentityError) as duplicate:
        service.create_staff(token, "Айша", "CONTACT.ONE", password, frozenset({Role.KITCHEN}))
    assert duplicate.value.code == "USER_EXISTS"
    with pytest.raises(IdentityError) as invalid_phone:
        service.create_staff(
            token,
            "Айша",
            "contact.invalid",
            password,
            frozenset({Role.KITCHEN}),
            phone="+79001234567",
        )
    assert "phone" in invalid_phone.value.field_errors
    with TestClient(create_app(settings)) as client:
        legacy = client.post(
            "/api/v1/auth/login",
            headers=headers(client),
            json={"phone": "+77010000011", "password": password},
        )
        assert legacy.status_code == 422 and password not in legacy.text
