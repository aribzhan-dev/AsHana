import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from ashana.bootstrap.settings import Settings
from ashana.modules.identity.domain.models import (
    IdentityError,
    Role,
    Session,
    normalize_login,
    normalize_name,
    permissions_for,
    validate_password,
)
from ashana.modules.identity.infrastructure.security import ArgonPasswords, KazakhstanMobilePhones


@pytest.mark.parametrize("name", ["Әлия", "Нұр-Сұлтан", "О’Коннор", "  Ирина  ", "Jose\u0301"])
def test_unicode_names(name: str) -> None:
    assert normalize_name(name) == __import__("unicodedata").normalize("NFC", name.strip())


@pytest.mark.parametrize("name", ["", "Анна2", "A--B", "A\n", "\tАнна", "-А", "А_Б"])
def test_invalid_names(name: str) -> None:
    with pytest.raises(IdentityError):
        normalize_name(name)


@pytest.mark.parametrize("phone", ["+77010000001", "+7 (701) 000-00-01"])
def test_kazakhstan_mobile(phone: str) -> None:
    assert KazakhstanMobilePhones().normalize(phone) == "+77010000001"


@pytest.mark.parametrize(
    "phone",
    [
        "+74951234567",
        "+79001234567",
        "+77271234567",
        "87010000001",
        "+77010000001abc",
        "+77010000001\n",
    ],
)
def test_non_mobile_or_non_kazakhstan_rejected(phone: str) -> None:
    with pytest.raises(IdentityError):
        KazakhstanMobilePhones().normalize(phone)


def test_argon_passwords_preserve_spaces_and_do_not_echo() -> None:
    passwords = ArgonPasswords()
    password = secrets.token_urlsafe(16) + " "
    hashed = passwords.hash(password)
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert passwords.verify(hashed, password)
    assert not passwords.verify(hashed, password.strip())
    assert not passwords.verify(None, password)
    assert not passwords.needs_rehash(hashed)
    validate_password(" " * 4)
    with pytest.raises(IdentityError):
        validate_password("abc")


def test_session_expiry_and_permissions() -> None:
    now = datetime.now(UTC)
    session = Session(uuid4(), uuid4(), "a" * 64, now, now + timedelta(seconds=1))
    assert session.active_at(now)
    assert not session.active_at(now + timedelta(seconds=1))
    assert "identity.manage" not in permissions_for(frozenset({Role.MANAGER}))
    assert permissions_for(frozenset({Role.ADMIN})) == {"identity.manage"}


def test_production_settings_reject_local_shortcuts() -> None:
    for options in ({"demo_identity": True}, {"cookie_secure": False}):
        with pytest.raises(ValidationError):
            Settings(db_password=SecretStr("placeholder"), environment="production", **options)  # type: ignore[arg-type]
    assert Settings(
        db_password=SecretStr("placeholder"),
        environment="production",
        cookie_secure=True,
        demo_identity=False,
    ).session_cookie.startswith("__Host-")


def test_http_validation_does_not_echo_extra_fields() -> None:
    from fastapi.testclient import TestClient

    from ashana.bootstrap.app import create_app

    app = create_app(readiness_probe=lambda: True)
    app.state.identity = object()
    app.state.settings = Settings(
        db_password=SecretStr("placeholder"),
        environment="test",
        cookie_secure=False,
        allowed_origins=["http://testserver"],
    )
    with TestClient(app) as client:
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        result = client.post(
            "/api/v1/auth/login",
            json={
                "login": 123,
                "password": "placeholder-secret",
                "private-key-name": "hidden",
            },
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        )
        assert result.status_code == 422
        assert "login" in result.json()["field_errors"]
        assert "placeholder-secret" not in result.text
        assert "private-key-name" not in result.text


@pytest.mark.parametrize(
    "value,expected", [("Admin", "admin"), (" kassir.01 ", "kassir.01"), ("staff_123", "staff_123")]
)
def test_login_normalization(value: str, expected: str) -> None:
    assert normalize_login(value) == expected


@pytest.mark.parametrize(
    "value", ["ab", "1admin", "+77010000001", "админ", "admin\n", "Kaa", "a" * 41, "a b"]
)
def test_invalid_logins(value: str) -> None:
    with pytest.raises(IdentityError):
        normalize_login(value)
