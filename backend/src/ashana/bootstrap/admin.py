from getpass import getpass

from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError
from ashana.modules.identity.infrastructure.database import PostgresIdentityUnitOfWork
from ashana.modules.identity.infrastructure.security import ArgonPasswords, KazakhstanMobilePhones


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    if settings.environment not in {"local", "test"} or not settings.demo_identity:
        raise SystemExit("Создание первого администратора доступно только в локальном режиме.")
    name = input("Имя администратора: ")
    login = input("Логин администратора: ")
    phone = input("Мобильный телефон Казахстана (необязательно, +7): ") or None
    password = getpass("Пароль (12–128 символов): ")
    if password != getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают.")
    engine = create_database_engine(settings)
    try:
        service = IdentityService(
            lambda: PostgresIdentityUnitOfWork(engine),
            ArgonPasswords(),
            KazakhstanMobilePhones(),
            allow_demo=True,
        )
        service.bootstrap_admin(name, login, password, phone)
        print("Администратор создан. Вход доступен через раздел «Для сотрудников».")
    except IdentityError as exc:
        raise SystemExit(exc.message) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
