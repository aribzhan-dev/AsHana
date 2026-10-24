import sys
from getpass import getpass

from sqlalchemy import Engine

from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError
from ashana.modules.identity.infrastructure.database import PostgresIdentityUnitOfWork
from ashana.modules.identity.infrastructure.security import ArgonPasswords, KazakhstanMobilePhones


def service(settings: Settings) -> tuple[IdentityService, Engine]:
    engine = create_database_engine(settings)
    return (
        IdentityService(
            lambda: PostgresIdentityUnitOfWork(engine),
            ArgonPasswords(),
            KazakhstanMobilePhones(),
            allow_demo=True,
        ),
        engine,
    )


def new_password() -> str:
    password = getpass("Пароль (4–128 символов): ")
    if password != getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают.")
    return password


def reset(settings: Settings) -> None:
    login = input("Логин администратора: ")
    password = new_password()
    identity, engine = service(settings)
    try:
        identity.recover_admin(login, password)
        print("Пароль администратора изменён. Все его сессии завершены.")
    except IdentityError as exc:
        raise SystemExit(exc.message) from None
    finally:
        engine.dispose()


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    if settings.environment not in {"local", "test"} or not settings.demo_identity:
        raise SystemExit("Команда доступна только в локальном режиме.")
    # `python -m ashana.bootstrap.admin reset` — forgotten administrator password.
    if sys.argv[1:] == ["reset"]:
        return reset(settings)
    name = input("Имя администратора: ")
    login = input("Логин администратора: ")
    phone = input("Мобильный телефон Казахстана (необязательно, +7): ") or None
    password = new_password()
    identity, engine = service(settings)
    try:
        identity.bootstrap_admin(name, login, password, phone)
        print("Администратор создан. Вход для сотрудников: /admin.")
    except IdentityError as exc:
        raise SystemExit(exc.message) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
