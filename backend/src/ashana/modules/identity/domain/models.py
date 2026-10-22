import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class IdentityError(Exception):
    def __init__(
        self, code: str, message: str, field_errors: dict[str, list[str]] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field_errors = field_errors or {}


class Role(StrEnum):
    KITCHEN = "kitchen"
    CASHIER = "cashier"
    STOREKEEPER = "storekeeper"
    MANAGER = "manager"
    ADMIN = "admin"


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.KITCHEN: frozenset({"kitchen.read", "kitchen.manage", "production.manage"}),
    Role.CASHIER: frozenset({"kitchen.read", "orders.fulfil", "pos.sell", "inventory.writeoff"}),
    Role.STOREKEEPER: frozenset({"inventory.manage"}),
    Role.MANAGER: frozenset(
        {
            "kitchen.read",
            "kitchen.manage",
            "production.manage",
            "orders.fulfil",
            "pos.sell",
            "pos.refund",
            "inventory.manage",
            "inventory.writeoff",
            "catalog.manage",
            "reporting.read",
            "finance.manage",
        }
    ),
    Role.ADMIN: frozenset({"identity.manage"}),
}


def permissions_for(roles: frozenset[Role]) -> frozenset[str]:
    return frozenset(permission for role in roles for permission in ROLE_PERMISSIONS[role])


def normalize_login(value: str) -> str:
    login = value.strip(" ")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{2,39}", login, flags=re.ASCII):
        raise IdentityError(
            "VALIDATION_ERROR",
            "Проверьте введённые данные",
            {
                "login": [
                    "Логин: 3–40 латинских букв, цифр, точек, дефисов "
                    "или подчёркиваний; начните с буквы"
                ]
            },
        )
    return login.lower()


def normalize_name(value: str) -> str:
    name = unicodedata.normalize("NFC", value.strip())
    valid = (
        bool(name)
        and len(name) <= 100
        and not any(unicodedata.category(char).startswith("C") for char in value)
    )
    previous_letter = False
    for char in name:
        category = unicodedata.category(char)
        if category.startswith("L"):
            previous_letter = True
        elif category.startswith("M") and previous_letter:
            continue
        elif char in " -'’" and previous_letter:
            previous_letter = False
        else:
            valid = False
    if not valid or not previous_letter:
        raise IdentityError(
            "VALIDATION_ERROR",
            "Проверьте введённые данные",
            {"name": ["Введите имя из букв, от 1 до 100 символов"]},
        )
    return name


def normalize_nickname(value: str) -> str:
    nickname = unicodedata.normalize("NFC", value.strip())
    if len(nickname) > 100 or any(unicodedata.category(c).startswith("C") for c in value):
        raise IdentityError(
            "VALIDATION_ERROR",
            "Проверьте никнейм",
            {"nickname": ["До 100 символов без управляющих знаков"]},
        )
    return nickname


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 128:
        raise IdentityError(
            "VALIDATION_ERROR",
            "Проверьте введённые данные",
            {"password": ["Пароль должен содержать от 12 до 128 символов"]},
        )


@dataclass(frozen=True)
class User:
    id: UUID
    login: str
    phone: str | None
    name: str
    password_hash: str = field(repr=False)
    roles: frozenset[str]
    created_at: datetime
    is_active: bool = True
    is_demo: bool = True
    permissions: frozenset[str] | None = None
    nickname: str = ""

    @property
    def effective_permissions(self) -> frozenset[str]:
        if self.permissions is not None:
            return self.permissions
        return frozenset(p for role in self.roles for p in ROLE_PERMISSIONS.get(role, frozenset()))


@dataclass(frozen=True)
class Session:
    id: UUID
    user_id: UUID
    token_hash: str = field(repr=False)
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def active_at(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now


@dataclass(frozen=True)
class Principal:
    user: User
    session: Session

    def require(self, permission: str) -> None:
        if permission not in self.user.effective_permissions:
            raise IdentityError("FORBIDDEN", "Недостаточно прав для этого действия")


@dataclass(frozen=True)
class RoleDefinition:
    code: str
    name: str
    permissions: frozenset[str]
    version: int


PERMISSIONS = frozenset(p for values in ROLE_PERMISSIONS.values() for p in values)
