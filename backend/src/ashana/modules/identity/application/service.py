import hashlib
import re
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
    PERMISSIONS,
    IdentityError,
    Principal,
    Role,
    RoleDefinition,
    Session,
    User,
    normalize_login,
    normalize_name,
    normalize_nickname,
    normalize_telegram,
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
            if not user or user.deleted_at:
                raise IdentityError("NOT_FOUND", "Сотрудник не найден")
            return user

    def _new_user(
        self, name: str, login: str, password: str, roles: frozenset[str], phone: str | None = None
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

    def set_nickname(
        self, token: str, user_id: UUID, nickname: str, expected_nickname: str
    ) -> User:
        nickname = normalize_nickname(nickname)
        with self.uow() as uow:
            principal = self._principal(uow, token)
            principal.require("identity.manage")
            user = uow.repository.user_by_id(user_id, lock=True)
            if not user:
                raise IdentityError("NOT_FOUND", "Сотрудник не найден")
            if user.nickname == nickname:
                return user
            if user.nickname != expected_nickname:
                raise IdentityError("CONFLICT", "Никнейм изменился. Обновите список сотрудников")
            uow.repository.update_nickname(user_id, nickname)
            uow.repository.audit(
                "nickname_updated",
                principal.user.id,
                user_id,
                self.clock(),
                {"nickname": [nickname]},
            )
            uow.commit()
            return replace(user, nickname=nickname)

    def create_staff(
        self,
        token: str,
        name: str,
        login: str,
        password: str,
        roles: frozenset[str],
        phone: str | None = None,
        nickname: str = "",
        telegram: str | None = None,
    ) -> User:
        # Authorize before expensive hashing, then recheck under the role-change lock.
        self.authenticate(token).require("identity.manage")
        user = replace(
            self._new_user(name, login, password, roles, phone),
            nickname=normalize_nickname(nickname),
            telegram=normalize_telegram(telegram),
        )
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
            self._validate_roles(uow.repository, roles)
            uow.repository.add_user(user)
            user = uow.repository.user_by_id(user.id) or user
            uow.repository.audit(
                "staff_created",
                principal.user.id,
                user.id,
                self.clock(),
                {"roles": sorted(user.roles)},
            )
            uow.commit()
            return user

    def assign_roles(self, token: str, user_id: UUID, roles: frozenset[str]) -> User:
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
            self._validate_roles(uow.repository, roles)
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
            result = uow.repository.user_by_id(user_id) or replace(target, roles=roles)
            uow.commit()
            return result

    def staff_member(self, token: str, user_id: UUID) -> User:
        with self.uow() as uow:
            self._principal(uow, token).require("identity.manage")
            user = uow.repository.user_by_id(user_id)
            if not user or user.deleted_at:
                raise IdentityError("NOT_FOUND", "Сотрудник не найден")
            return user

    def update_profile(
        self,
        token: str,
        user_id: UUID,
        name: str,
        phone: str | None,
        telegram: str | None,
        nickname: str,
    ) -> User:
        name = normalize_name(name)
        phone = self.phones.normalize(phone) if phone and phone.strip() else None
        telegram = normalize_telegram(telegram)
        nickname = normalize_nickname(nickname)
        with self.uow() as uow:
            principal = self._principal(uow, token)
            principal.require("identity.manage")
            target = uow.repository.user_by_id(user_id, lock=True)
            if not target or target.deleted_at:
                raise IdentityError("NOT_FOUND", "Сотрудник не найден")
            uow.repository.update_profile(user_id, name, phone, telegram, nickname)
            uow.repository.audit("profile_updated", principal.user.id, user_id, self.clock(), {})
            uow.commit()
            return replace(target, name=name, phone=phone, telegram=telegram, nickname=nickname)

    def _guard_admin_access(self, uow: IdentityUnitOfWork, actor: User, target: User) -> None:
        if target.id == actor.id:
            raise IdentityError("FORBIDDEN", "Свой доступ меняет другой администратор")
        if Role.ADMIN in target.roles and target.is_active and uow.repository.admin_count() <= 1:
            raise IdentityError("LAST_ADMIN", "Нельзя отключить последнего администратора")

    def set_active(self, token: str, user_id: UUID, active: bool) -> User:
        """Block or unblock an employee; a blocked one is signed out everywhere."""
        with self.uow() as uow:
            uow.repository.lock_role_changes()
            principal = self._principal(uow, token)
            principal.require("identity.manage")
            target = uow.repository.user_by_id(user_id, lock=True)
            if not target or target.deleted_at:
                raise IdentityError("NOT_FOUND", "Сотрудник не найден")
            if target.is_active == active:
                return target
            if not active:
                self._guard_admin_access(uow, principal.user, target)
            uow.repository.set_active(user_id, active)
            if not active:
                uow.repository.revoke_user_sessions(user_id, self.clock())
            uow.repository.audit(
                "staff_unblocked" if active else "staff_blocked",
                principal.user.id,
                user_id,
                self.clock(),
                {},
            )
            uow.commit()
            return replace(target, is_active=active)

    def delete_staff(self, token: str, user_id: UUID) -> None:
        """Archive: history keeps the name, the account disappears and cannot log in."""
        with self.uow() as uow:
            uow.repository.lock_role_changes()
            principal = self._principal(uow, token)
            principal.require("identity.manage")
            target = uow.repository.user_by_id(user_id, lock=True)
            if not target or target.deleted_at:
                return
            self._guard_admin_access(uow, principal.user, target)
            now = self.clock()
            uow.repository.archive_user(user_id, now)
            uow.repository.revoke_user_sessions(user_id, now)
            uow.repository.audit("staff_deleted", principal.user.id, user_id, now, {})
            uow.commit()

    def reset_password(self, token: str, user_id: UUID, password: str) -> User:
        """An administrator sets a new password for an employee who forgot theirs."""
        # Authorize before expensive hashing, then recheck inside the transaction.
        self.authenticate(token).require("identity.manage")
        validate_password(password)
        hashed = self.passwords.hash(password)
        with self.uow() as uow:
            principal = self._principal(uow, token)
            principal.require("identity.manage")
            target = uow.repository.user_by_id(user_id, lock=True)
            if not target or target.deleted_at:
                raise IdentityError("NOT_FOUND", "Сотрудник не найден")
            if target.id == principal.user.id:
                raise IdentityError(
                    "FORBIDDEN",
                    "Свой пароль меняет другой администратор или команда на сервере",
                )
            uow.repository.update_password_hash(user_id, hashed)
            # Whoever knew the old password loses access everywhere at once.
            uow.repository.revoke_user_sessions(user_id, self.clock())
            uow.repository.audit("password_reset", principal.user.id, user_id, self.clock(), {})
            uow.commit()
            return target

    def recover_admin(self, login: str, password: str) -> User:
        """Local server command for an administrator who forgot their own password."""
        if not self.allow_demo:
            raise IdentityError("FORBIDDEN", "Восстановление доступно только в локальном режиме")
        validate_password(password)
        hashed = self.passwords.hash(password)
        with self.uow() as uow:
            user = uow.repository.find_user(normalize_login(login), lock=True)
            if not user or Role.ADMIN not in user.roles:
                raise IdentityError("NOT_FOUND", "Администратор с таким логином не найден")
            uow.repository.update_password_hash(user.id, hashed)
            uow.repository.revoke_user_sessions(user.id, self.clock())
            uow.repository.audit("admin_password_recovered", None, user.id, self.clock(), {})
            uow.commit()
            return user

    def _validate_roles(self, repository: IdentityRepository, assigned: frozenset[str]) -> None:
        known = {role.code for role in repository.role_definitions()}
        if not assigned or not assigned <= known:
            raise IdentityError(
                "VALIDATION_ERROR",
                "Выберите существующие роли",
                {"roles": ["Выберите существующие роли"]},
            )

    def list_staff(self, token: str, offset: int = 0, limit: int = 100) -> list[User]:
        with self.uow() as uow:
            self._principal(uow, token).require("identity.manage")
            return uow.repository.list_users(max(0, offset), min(100, max(1, limit)))

    def list_roles(self, token: str) -> list[RoleDefinition]:
        with self.uow() as uow:
            self._principal(uow, token).require("identity.manage")
            return uow.repository.role_definitions()

    def save_role(
        self, token: str, code: str, name: str, permissions: frozenset[str], version: int | None
    ) -> RoleDefinition:
        if (
            not re.fullmatch(r"[a-z][a-z0-9_]{2,19}", code)
            or not name.strip()
            or len(name.strip()) > 100
        ):
            raise IdentityError(
                "VALIDATION_ERROR",
                "Укажите название роли и код из 3–20 латинских букв, цифр и подчёркиваний",
            )
        if not permissions <= PERMISSIONS:
            raise IdentityError("VALIDATION_ERROR", "Выберите допустимые права")
        # Preserve a guaranteed recovery role; its other permissions remain editable.
        if code == "admin" and "identity.manage" not in permissions:
            raise IdentityError(
                "LAST_ADMIN", "У роли администратора необходимо сохранить управление сотрудниками"
            )
        with self.uow() as uow:
            uow.repository.lock_role_changes()
            actor = self._principal(uow, token)
            actor.require("identity.manage")
            existing = next(
                (role for role in uow.repository.role_definitions() if role.code == code), None
            )
            if (existing is None and version is not None) or (
                existing is not None and existing.version != version
            ):
                raise IdentityError("CONFLICT", "Роль уже изменена или код занят. Обновите список")
            result = RoleDefinition(
                code, name.strip(), permissions, (existing.version + 1) if existing else 1
            )
            uow.repository.save_role(result, existing is None)
            if existing and existing.permissions != permissions:
                uow.repository.revoke_role_sessions(code, self.clock())
            uow.repository.audit(
                "role_updated" if existing else "role_created",
                actor.user.id,
                actor.user.id,
                self.clock(),
                {
                    "role": [code],
                    "name": [result.name],
                    "before": sorted(existing.permissions) if existing else [],
                    "after": sorted(permissions),
                },
            )
            uow.commit()
            return result

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
