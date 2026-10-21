import hashlib
import secrets
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ashana.modules.identity.application.ports import (
    IdentityRepository,
    IdentityUnitOfWork,
    Passwords,
    Phones,
)
from ashana.modules.identity.domain.models import (
    IdentityError,
    Principal,
    Role,
    Session,
    User,
    normalize_login,
    normalize_name,
    validate_password,
)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class IdentityService:
    def __init__(
        self,
        uow: Callable[[], IdentityUnitOfWork],
        passwords: Passwords,
        phones: Phones,
        *,
        allow_demo: bool,
        session_seconds: int = 43200,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        login_limit: int = 10,
        ip_limit: int = 60,
    ) -> None:
        self.uow = uow
        self.passwords = passwords
        self.phones = phones
        self.allow_demo = allow_demo
        self.session_seconds = session_seconds
        self.clock = clock
        self.login_limit = login_limit
        self.ip_limit = ip_limit

    def _principal(self, uow: IdentityUnitOfWork, token: str) -> Principal:
        return self.principal(uow.repository, token)

    def principal(self, repository: IdentityRepository, token: str) -> Principal:
        session = repository.session_for_token(token_digest(token))
        if not session or not session.active_at(self.clock()):
            raise IdentityError("UNAUTHENTICATED", "Войдите в аккаунт сотрудника")
        user = repository.user_by_id(session.user_id)
        if not user or not user.is_active or (user.is_demo and not self.allow_demo):
            raise IdentityError("UNAUTHENTICATED", "Войдите в аккаунт сотрудника")
        return Principal(user, session)

    def authenticate(self, token: str) -> Principal:
        with self.uow() as uow:
            return self._principal(uow, token)

    def _limit(self, key: str, limit: int) -> None:
        with self.uow() as uow:
            allowed = uow.repository.consume_rate(token_digest(key), self.clock(), limit, 900)
            # Failed authentication must not roll back consumed rate-limit attempts.
            uow.commit()
        if not allowed:
            raise IdentityError("RATE_LIMITED", "Слишком много попыток. Попробуйте через 15 минут")

    def login(
        self, login: str, password: str, ip: str, previous_token: str = ""
    ) -> tuple[User, str]:
        self._limit(f"login-ip:{ip}", self.ip_limit)
        try:
            normalized = normalize_login(login)
        except IdentityError:
            normalized = ""
        self._limit(f"login-name:{normalized or 'invalid'}", self.login_limit)
        with self.uow() as uow:
            user = uow.repository.find_user(normalized, lock=True)
            verified = self.passwords.verify(user.password_hash if user else None, password)
            if (
                not user
                or not verified
                or not user.is_active
                or (user.is_demo and not self.allow_demo)
            ):
                raise IdentityError("INVALID_CREDENTIALS", "Неверный логин или пароль")
            if self.passwords.needs_rehash(user.password_hash):
                uow.repository.update_password_hash(user.id, self.passwords.hash(password))
            if previous_token:
                previous = uow.repository.session_for_token(token_digest(previous_token))
                if previous:
                    uow.repository.revoke_session(previous.id, self.clock())
            token = secrets.token_urlsafe(32)
            now = self.clock()
            uow.repository.add_session(
                Session(
                    uuid4(),
                    user.id,
                    token_digest(token),
                    now,
                    now + timedelta(seconds=self.session_seconds),
                )
            )
            uow.repository.audit("login", user.id, user.id, now, {})
            uow.commit()
            return user, token

    def logout(self, token: str) -> None:
        with self.uow() as uow:
            session = uow.repository.session_for_token(token_digest(token))
            if session and session.revoked_at is None:
                uow.repository.revoke_session(session.id, self.clock())
                uow.repository.audit("logout", session.user_id, session.id, self.clock(), {})
            uow.commit()

    def sessions(self, token: str) -> tuple[Principal, list[Session]]:
        with self.uow() as uow:
            principal = self._principal(uow, token)
            return principal, uow.repository.sessions_for_user(principal.user.id, self.clock())

    def revoke_session(self, token: str, session_id: UUID) -> bool:
        with self.uow() as uow:
            principal = self._principal(uow, token)
            target = uow.repository.session_by_id(session_id)
            if not target or target.user_id != principal.user.id:
                raise IdentityError("NOT_FOUND", "Сессия не найдена")
            if target.revoked_at is None:
                uow.repository.revoke_session(session_id, self.clock())
                uow.repository.audit(
                    "session_revoked", principal.user.id, session_id, self.clock(), {}
                )
            uow.commit()
            return target.id == principal.session.id

    def find_staff(self, token: str, login: str) -> User:
        with self.uow() as uow:
            principal = self._principal(uow, token)
            principal.require("identity.manage")
            user = uow.repository.find_user(normalize_login(login))
            if not user:
                raise IdentityError("NOT_FOUND", "Сотрудник не найден")
            return user

    def _new_user(
        self, name: str, login: str, password: str, roles: frozenset[Role], phone: str | None = None
    ) -> User:
        validate_password(password)
        if not roles:
            raise IdentityError(
                "VALIDATION_ERROR",
                "Выберите хотя бы одну роль",
                {"roles": ["Выберите хотя бы одну роль"]},
            )
        return User(
            uuid4(),
            normalize_login(login),
            self.phones.normalize(phone) if phone else None,
            normalize_name(name),
            self.passwords.hash(password),
            roles,
            self.clock(),
        )

    def create_staff(
        self,
        token: str,
        name: str,
        login: str,
        password: str,
        roles: frozenset[Role],
        phone: str | None = None,
    ) -> User:
        # Authorize before expensive hashing, then recheck under the role-change lock.
        self.authenticate(token).require("identity.manage")
        user = self._new_user(name, login, password, roles, phone)
        with self.uow() as uow:
            uow.repository.lock_role_changes()
            principal = self._principal(uow, token)
            principal.require("identity.manage")
            if uow.repository.find_user(user.login):
                raise IdentityError(
                    "USER_EXISTS",
                    "Этот логин уже используется",
                    {"login": ["Этот логин уже используется"]},
                )
            uow.repository.add_user(user)
            uow.repository.audit(
                "staff_created",
                principal.user.id,
                user.id,
                self.clock(),
                {"roles": sorted(user.roles)},
            )
            uow.commit()
            return user

    def assign_roles(self, token: str, user_id: UUID, roles: frozenset[Role]) -> User:
        with self.uow() as uow:
            uow.repository.lock_role_changes()
            principal = self._principal(uow, token)
            principal.require("identity.manage")
            if not roles:
                raise IdentityError(
                    "VALIDATION_ERROR",
                    "Выберите хотя бы одну роль",
                    {"roles": ["Выберите хотя бы одну роль"]},
                )
            target = uow.repository.user_by_id(user_id, lock=True)
            if not target:
                raise IdentityError("NOT_FOUND", "Сотрудник не найден")
            if (
                Role.ADMIN in target.roles
                and Role.ADMIN not in roles
                and uow.repository.admin_count() <= 1
            ):
                raise IdentityError("LAST_ADMIN", "Нельзя убрать роль последнего администратора")
            if target.roles != roles:
                uow.repository.update_roles(user_id, roles)
                uow.repository.revoke_user_sessions(user_id, self.clock())
                uow.repository.audit(
                    "roles_changed",
                    principal.user.id,
                    user_id,
                    self.clock(),
                    {"before": sorted(target.roles), "after": sorted(roles)},
                )
            uow.commit()
            return replace(target, roles=roles)

    def bootstrap_admin(
        self, name: str, login: str, password: str, phone: str | None = None
    ) -> User:
        if not self.allow_demo:
            raise IdentityError("FORBIDDEN", "Локальное создание администратора отключено")
        user = self._new_user(name, login, password, frozenset({Role.ADMIN, Role.MANAGER}), phone)
        with self.uow() as uow:
            uow.repository.lock_role_changes()
            if uow.repository.admin_count() > 0:
                raise IdentityError("ADMIN_EXISTS", "Администратор уже создан")
            if uow.repository.find_user(user.login):
                raise IdentityError(
                    "USER_EXISTS",
                    "Этот логин уже используется",
                    {"login": ["Этот логин уже используется"]},
                )
            uow.repository.add_user(user)
            uow.repository.audit(
                "admin_bootstrapped", None, user.id, self.clock(), {"roles": sorted(user.roles)}
            )
            uow.commit()
            return user
