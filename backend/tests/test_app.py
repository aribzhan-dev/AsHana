import logging
from pathlib import Path
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pytest import LogCaptureFixture

from ashana.bootstrap.app import create_app
from ashana.bootstrap.database import SCHEMA_REVISION
from ashana.bootstrap.settings import Settings


def test_liveness_survives_failed_database() -> None:
    with TestClient(create_app(readiness_probe=lambda: False)) as client:
        assert client.get("/api/v1/health/live").json()["status"] == "ok"
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["message"] == "Сервис временно недоступен. Попробуйте позже"
    assert str(UUID(response.json()["request_id"])) == response.headers["X-Request-ID"]


def test_ready_and_unique_request_ids() -> None:
    with TestClient(create_app(readiness_probe=lambda: True)) as client:
        first = client.get("/api/v1/health/ready", headers={"X-Request-ID": "untrusted"})
        second = client.get("/api/v1/health/ready")
    assert first.status_code == 200
    assert first.json() == {"status": "ok", "service": "ashana-api"}
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]
    UUID(first.headers["X-Request-ID"])


def test_unknown_route_and_wrong_method_are_localized() -> None:
    with TestClient(create_app(readiness_probe=lambda: True)) as client:
        missing = client.get("/missing")
        wrong_method = client.post("/api/v1/health/live")
    assert missing.status_code == 404
    assert missing.json()["message"] == "Страница не найдена"
    assert wrong_method.status_code == 405
    assert wrong_method.json()["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in wrong_method.headers["allow"]


def app_with_validation() -> FastAPI:
    app = create_app(readiness_probe=lambda: True)

    @app.get("/test/quantity")
    def quantity(value: int) -> dict[str, int]:
        return {"value": value}

    return app


def test_validation_does_not_echo_input_or_query(caplog: LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ashana")
    with TestClient(app_with_validation()) as client:
        response = client.get("/test/quantity?value=sensitive-value")
    assert response.status_code == 422
    assert response.json()["field_errors"] == {"value": ["Введите целое число"]}
    assert "sensitive-value" not in response.text
    assert "sensitive-value" not in "\n".join(
        record.message for record in caplog.records if record.name == "ashana"
    )


def test_unexpected_error_is_redacted(caplog: LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ashana")

    def failed_probe() -> bool:
        raise RuntimeError("private-database-details")

    with TestClient(create_app(readiness_probe=failed_probe)) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 500
    assert response.json()["message"] == "Не удалось выполнить действие"
    assert "private-database-details" not in response.text + caplog.text


def test_schema_revision_matches_migration_head() -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    assert ScriptDirectory.from_config(config).get_heads() == [SCHEMA_REVISION]


def test_settings_handle_special_characters_without_exposing_password() -> None:
    settings = Settings(db_password=SecretStr("synthetic:@/%example"))
    assert settings.database_url.password == "synthetic:@/%example"
    assert "synthetic" not in repr(settings)
    assert "synthetic" not in str(settings.database_url)


def test_openapi_generation_needs_no_database() -> None:
    schema = create_app().openapi()
    assert schema["paths"]["/api/v1/health/ready"]["get"]["operationId"] == "getReadiness"
