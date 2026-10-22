"""Back up the local AsHana database and prove the backup restores.

    python3 -I scripts/backup_db.py backup            # backups/ashana-<time>.dump, keeps 14
    python3 -I scripts/backup_db.py verify FILE        # restore into a scratch DB and compare
    python3 -I scripts/backup_db.py restore FILE --yes # REPLACE the working DB (destructive)

Dumps contain personal and financial data: they are written with 0600 permissions into the
ignored backups/ folder and must never be published or sent anywhere.
"""

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / "backups"
SCRATCH = "ashana_restore_check"
COMPOSE = ["docker", "compose", "--file", str(ROOT / "compose.yaml")]
# Tables whose row counts must survive a round trip.
TABLES = [
    "identity_users",
    "inventory_items",
    "inventory_batches",
    "inventory_movements",
    "inventory_invoices",
    "catalog_periods",
    "catalog_entries",
    "checkout_drafts",
    "orders",
    "order_events",
    "pos_attempts",
    "pos_returns",
    "finance_expenses",
    "payroll_workers",
    "payroll_shifts",
    "payroll_payments",
    "inventory_item_images",
]


def db(*args: str, stdin: bytes | None = None, capture: bool = True) -> bytes:
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", "db", *args],
        input=stdin,
        capture_output=capture,
        check=False,
    )
    if result.returncode:
        message = (result.stderr or b"").decode(errors="replace").strip()[-400:]
        raise SystemExit(f"Команда в контейнере БД не выполнена: {message}")
    return result.stdout or b""


def psql(database: str, sql: str) -> str:
    return db("psql", "-U", "postgres", "-d", database, "-tAc", sql).decode().strip()


def counts(database: str) -> dict[str, str]:
    return {table: psql(database, f"SELECT count(*) FROM {table}") for table in TABLES}


def backup(keep: int) -> Path:
    BACKUPS.mkdir(mode=0o700, exist_ok=True)
    target = BACKUPS / f"ashana-{datetime.now():%Y%m%d-%H%M%S}.dump"
    data = db("pg_dump", "-U", "postgres", "-d", "ashana", "-Fc")
    old_umask = os.umask(0o077)
    try:
        target.write_bytes(data)
    finally:
        os.umask(old_umask)
    digest = hashlib.sha256(data).hexdigest()
    (target.with_suffix(".sha256")).write_text(f"{digest}  {target.name}\n")
    size = len(data) // 1024
    print(f"Резервная копия: {target.relative_to(ROOT)} ({size} КБ), sha256 {digest[:16]}…")
    dumps = sorted(BACKUPS.glob("ashana-*.dump"))
    for old in dumps[:-keep]:
        old.unlink()
        old.with_suffix(".sha256").unlink(missing_ok=True)
        print(f"Удалена старая копия: {old.name}")
    return target


def checked(path: Path) -> bytes:
    data = path.read_bytes()
    checksum = path.with_suffix(".sha256")
    if checksum.exists() and checksum.read_text().split()[0] != hashlib.sha256(data).hexdigest():
        raise SystemExit("Контрольная сумма не совпадает: файл копии повреждён.")
    return data


def verify(path: Path) -> None:
    data = checked(path)
    psql("postgres", f"DROP DATABASE IF EXISTS {SCRATCH}")
    psql("postgres", f"CREATE DATABASE {SCRATCH}")
    try:
        # Same owners and grants as a real restore, so role problems surface here.
        db("pg_restore", "-U", "postgres", "-d", SCRATCH, "--exit-on-error", stdin=data)
        runtime = psql(
            SCRATCH,
            "SELECT has_table_privilege('ashana_app', 'orders', 'INSERT')"
            " AND NOT has_table_privilege('ashana_app', 'orders', 'DELETE')",
        )
        print(f"Права runtime-роли сохранены: {'да' if runtime == 't' else 'НЕТ'}")
        live, restored = counts("ashana"), counts(SCRATCH)
        version = psql(SCRATCH, "SELECT version_num FROM alembic_version")
        print(f"Схема в копии: {version}")
        width = max(len(t) for t in TABLES)
        for table in TABLES:
            mark = "ok" if live[table] == restored[table] else "ИЗМЕНИЛОСЬ ПОСЛЕ КОПИИ"
            print(
                f"  {table:<{width}}  копия {restored[table]:>6}  сейчас {live[table]:>6}  {mark}"
            )
        print("Копия восстанавливается. Расхождения означают записи, сделанные после копии.")
    finally:
        psql("postgres", f"DROP DATABASE IF EXISTS {SCRATCH}")


def restore(path: Path) -> None:
    data = checked(path)
    print("Останавливаю API и сайт; база ashana будет заменена копией.")
    subprocess.run([*COMPOSE, "stop", "web", "api"], check=True)
    try:
        psql("postgres", "DROP DATABASE ashana WITH (FORCE)")
        psql("postgres", "CREATE DATABASE ashana OWNER ashana_migrator")
        psql("ashana", "REVOKE ALL ON DATABASE ashana FROM PUBLIC")
        psql("ashana", "GRANT CONNECT ON DATABASE ashana TO ashana_app")
        db("pg_restore", "-U", "postgres", "-d", "ashana", "--exit-on-error", stdin=data)
    finally:
        subprocess.run([*COMPOSE, "up", "--detach", "--wait", "api", "web"], check=False)
    print("Восстановление завершено.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--keep", type=int, default=14)
    v = sub.add_parser("verify")
    v.add_argument("file", type=Path)
    r = sub.add_parser("restore")
    r.add_argument("file", type=Path)
    r.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if args.command == "backup":
        backup(args.keep)
    elif args.command == "verify":
        verify(args.file)
    else:
        if not args.yes or input("Введите ЗАМЕНИТЬ для подтверждения: ") != "ЗАМЕНИТЬ":
            sys.exit("Отменено: рабочая база не изменена.")
        restore(args.file)


if __name__ == "__main__":
    main()
