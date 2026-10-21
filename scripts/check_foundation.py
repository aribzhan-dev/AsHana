"""Exercise an isolated local stack without reading or writing an .env file."""

import argparse
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальная проверка FOUNDATION-01")
    parser.add_argument("--web-port", type=int, default=18080)
    parser.add_argument("--api-port", type=int, default=18000)
    parser.add_argument("--identity", action="store_true")
    parser.add_argument("--keep-running", action="store_true", help="Оставить стенд для просмотра")
    parser.add_argument(
        "--skip-browser", action="store_true", help="Не запускать браузерные проверки"
    )
    args = parser.parse_args()
    project = f"ashana-check-{secrets.token_hex(3)}"
    environment = {
        **os.environ,
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "ASHANA_MIGRATION_PASSWORD": secrets.token_urlsafe(32),
        "ASHANA_APP_PASSWORD": secrets.token_urlsafe(32),
        "ASHANA_WEB_PORT": str(args.web_port),
        "ASHANA_API_PORT": str(args.api_port),
        "ASHANA_E2E_URL": f"http://127.0.0.1:{args.web_port}",
        "ASHANA_TEST_PASSWORD": secrets.token_urlsafe(24),
    }
    if not args.identity:
        environment.pop("ASHANA_TEST_PASSWORD", None)
    compose = [
        "docker",
        "compose",
        "--file",
        str(ROOT / "compose.yaml"),
        "--env-file",
        os.devnull,
        "--project-name",
        project,
    ]

    def run(*arguments: str, capture: bool = False) -> str:
        result = subprocess.run(
            [*compose, *arguments],
            cwd=ROOT,
            env=environment,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
        )
        return result.stdout or ""

    def get(path: str) -> tuple[int, dict[str, object]]:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{args.web_port}{path}", timeout=8
            ) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def wait_ready() -> None:
        for _ in range(40):
            try:
                if get("/api/v1/health/ready")[0] == 200:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(1)
        raise RuntimeError("Сервис не восстановился после запуска БД")

    success = False
    try:
        run("config", "--quiet")
        run("build", "db", "migrate", "api", "web")
        run("up", "--detach", "--wait", "db")
        run(
            "run",
            "--rm",
            "--no-deps",
            "migrate",
            "alembic",
            "upgrade",
            "0001_foundation",
        )
        if args.identity:
            run("run", "--rm", "--no-deps", "migrate", "alembic", "upgrade", "0002_identity")
            legacy_seed = (
                "INSERT INTO identity_users "
                "(id, phone, name, password_hash, is_active, is_demo, created_at) "
                "VALUES ('00000000-0000-0000-0000-000000000001', '+77010000199', 'Проверка', "
                "'test-only-unusable', true, true, now()); "
                "INSERT INTO identity_user_roles (user_id, role) "
                "VALUES ('00000000-0000-0000-0000-000000000001', 'kitchen'); "
                "INSERT INTO identity_sessions (id, user_id, token_hash, created_at, expires_at) "
                "VALUES ('00000000-0000-0000-0000-000000000002', "
                "'00000000-0000-0000-0000-000000000001', repeat('f', 64), "
                "now(), now() + interval '1 hour');"
            )
            run(
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "postgres",
                "-d",
                "ashana",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                legacy_seed,
            )
        run("up", "--detach", "--wait", "--wait-timeout", "180")
        assert get("/api/v1/health/ready")[0] == 200
        run("run", "--rm", "--no-deps", "migrate")
        assert get("/api/v1/health/ready")[0] == 200
        if args.identity:
            preserved = run(
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "postgres",
                "-d",
                "ashana",
                "-tA",
                "-c",
                "SELECT count(*) FROM identity_users u "
                "JOIN identity_user_roles r ON r.user_id=u.id "
                "JOIN identity_sessions s ON s.user_id=u.id "
                "WHERE u.id='00000000-0000-0000-0000-000000000001' "
                "AND u.login='staff_00000000000000000000000000000001' "
                "AND u.phone='+77010000199' AND u.password_hash='test-only-unusable' "
                "AND r.role='kitchen' AND s.token_hash=repeat('f',64) AND s.revoked_at IS NULL;",
                capture=True,
            )
            assert preserved.strip() == "1", "Миграция должна сохранить аккаунт, роль и сессию"
        permission_query = (
            "SELECT current_user, "
            "has_schema_privilege(current_user, 'public', 'CREATE'), "
            "has_database_privilege(current_user, 'ashana', 'CREATE'), "
            "has_database_privilege(current_user, 'ashana', 'TEMP'), "
            "has_table_privilege(current_user, 'alembic_version', 'SELECT'), "
            "has_table_privilege(current_user, 'alembic_version', 'UPDATE'), "
            "rolsuper, rolcreaterole FROM pg_roles WHERE rolname = current_user;"
        )
        permissions = run(
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'PGPASSWORD="$ASHANA_APP_PASSWORD" psql -h 127.0.0.1 -U ashana_app '
            '-d ashana -tA -v ON_ERROR_STOP=1 -c "$1"',
            "check",
            permission_query,
            capture=True,
        )
        assert permissions.strip() == "ashana_app|f|f|f|t|f|f|f", permissions
        print("Миграции повторяемы; runtime-роль ограничена.", flush=True)
        run("stop", "db")
        assert get("/api/v1/health/live")[0] == 200
        status, body = get("/api/v1/health/ready")
        assert status == 503 and body["code"] == "SERVICE_UNAVAILABLE"
        run("start", "db")
        wait_ready()
        print("Отказ БД и восстановление проверены.", flush=True)
        run("stop", "api")
        status, body = get("/api/v1/health/ready")
        assert status == 503 and body["code"] == "SERVICE_UNAVAILABLE"
        run("start", "api")
        wait_ready()
        print("Отказ API и русский ответ reverse proxy проверены.", flush=True)
        if args.identity:
            run("build", "test")
            run(
                "run",
                "--rm",
                "--no-deps",
                "-e",
                "ASHANA_TEST_PASSWORD",
                "test",
                "pytest",
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            )
        if not args.skip_browser:
            browser = subprocess.run(
                ["pnpm", "test:e2e"],
                cwd=ROOT / "frontend",
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            output = browser.stdout + browser.stderr
            synthetic_password = environment.get("ASHANA_TEST_PASSWORD", "")
            if synthetic_password:
                output = output.replace(synthetic_password, "[REDACTED]")
                # Playwright failure context can contain a filled password input.
                for artifact in (ROOT / "frontend" / "test-results").rglob("*"):
                    if artifact.is_file() and artifact.suffix in (".md", ".txt", ".json"):
                        content = artifact.read_text()
                        if synthetic_password in content:
                            artifact.write_text(content.replace(synthetic_password, "[REDACTED]"))
            print(output, flush=True)
            if browser.returncode:
                raise RuntimeError(
                    "Браузерные проверки не прошли; вывод очищен от тестового пароля"
                )
        success = True
        print(f"Проверки завершены. Проект Docker: {project}.", flush=True)
    except Exception:
        diagnostic = subprocess.run(
            [
                *compose,
                "logs",
                "--no-color",
                "--tail",
                "60",
                "db",
                "migrate",
                "api",
                "web",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        redacted = diagnostic.stdout + diagnostic.stderr
        for key in (
            "POSTGRES_PASSWORD",
            "ASHANA_MIGRATION_PASSWORD",
            "ASHANA_APP_PASSWORD",
            "ASHANA_TEST_PASSWORD",
        ):
            if key in environment:
                redacted = redacted.replace(environment[key], "[REDACTED]")
        print(redacted, flush=True)
        raise
    finally:
        if not (success and args.keep_running):
            run("down")
        else:
            print(f"Стенд оставлен: http://127.0.0.1:{args.web_port}", flush=True)
        print("Volumes не удалялись.", flush=True)


if __name__ == "__main__":
    main()
