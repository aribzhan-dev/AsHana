from datetime import datetime, timedelta
from types import TracebackType
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    case,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Connection, Engine, RowMapping

from ashana.modules.identity.application.ports import IdentityRepository
from ashana.modules.identity.domain.models import Role, RoleDefinition, Session, User

metadata = MetaData()
users = Table(
    "identity_users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("login", String(40), nullable=False, unique=True),
    Column("phone", String(12), nullable=True),
    CheckConstraint("login ~ '^[a-z][a-z0-9._-]{2,39}$'", name="ck_identity_login"),
    Column("name", String(100), nullable=False),
    Column("nickname", String(100), nullable=False),
    Column("password_hash", String(256), nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("is_demo", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("phone ~ '^\\+7[0-9]{10}$'", name="ck_identity_phone"),
    CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="ck_identity_name"),
)
roles = Table(
    "identity_roles",
    metadata,
    Column("code", String(20), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("permissions", JSONB, nullable=False),
    Column("version", Integer, nullable=False),
)
user_roles = Table(
    "identity_user_roles",
    metadata,
    Column("user_id", Uuid, ForeignKey("identity_users.id"), primary_key=True),
    Column("role", String(20), ForeignKey("identity_roles.code"), primary_key=True),
)
sessions = Table(
    "identity_sessions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, ForeignKey("identity_users.id"), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    CheckConstraint("expires_at > created_at", name="ck_identity_session_expiry"),
    CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_identity_token_hash"),
    Index("ix_identity_sessions_user", "user_id"),
)
audit = Table(
    "identity_audit",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("actor_id", Uuid, ForeignKey("identity_users.id")),
    Column("subject_id", Uuid, nullable=False),
    Column("action", String(40), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("details", JSONB, nullable=False),
)
rate_limits = Table(
    "identity_rate_limits",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("attempts", Integer, nullable=False),
    CheckConstraint("attempts > 0", name="ck_identity_attempts"),
)


class PostgresIdentityRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def _user(self, row: RowMapping | None) -> User | None:
        if row is None:
            return None
        assigned = (
            self.connection.execute(
                select(user_roles.c.role).where(user_roles.c.user_id == row["id"])
            )
            .scalars()
            .all()
        )
        granted = self.connection.execute(
            select(roles.c.permissions).where(roles.c.code.in_(assigned))
        ).scalars()
        permissions = frozenset(p for group in granted for p in group)
        return User(
            row["id"],
            row["login"],
            row["phone"],
            row["name"],
            row["password_hash"],
            frozenset(assigned),
            row["created_at"],
            row["is_active"],
            row["is_demo"],
            permissions,
            row["nickname"],
        )

    def find_user(self, login: str, *, lock: bool = False) -> User | None:
        query = select(users).where(users.c.login == login)
        return self._user(
            self.connection.execute(query.with_for_update() if lock else query).mappings().first()
        )

    def user_by_id(self, user_id: UUID, *, lock: bool = False) -> User | None:
        query = select(users).where(users.c.id == user_id)
        return self._user(
            self.connection.execute(query.with_for_update() if lock else query).mappings().first()
        )

    def add_user(self, user: User) -> None:
        self.connection.execute(
            users.insert().values(
                id=user.id,
                login=user.login,
                phone=user.phone,
                name=user.name,
                nickname=user.nickname,
                password_hash=user.password_hash,
                created_at=user.created_at,
                is_active=user.is_active,
                is_demo=user.is_demo,
            )
        )
        self.connection.execute(
            user_roles.insert(), [{"user_id": user.id, "role": str(role)} for role in user.roles]
        )

    def update_nickname(self, user_id: UUID, nickname: str) -> None:
        self.connection.execute(
            users.update().where(users.c.id == user_id).values(nickname=nickname)
        )

    def update_roles(self, user_id: UUID, roles: frozenset[str]) -> None:
        self.connection.execute(user_roles.delete().where(user_roles.c.user_id == user_id))
        self.connection.execute(
            user_roles.insert(), [{"user_id": user_id, "role": str(role)} for role in roles]
        )

    def role_definitions(self) -> list[RoleDefinition]:
        return [
            RoleDefinition(row.code, row.name, frozenset(row.permissions), row.version)
            for row in self.connection.execute(select(roles).order_by(roles.c.name))
        ]

    def save_role(self, definition: RoleDefinition, create: bool) -> None:
        values = dict(
            name=definition.name,
            permissions=sorted(definition.permissions),
            version=definition.version,
        )
        if create:
            self.connection.execute(roles.insert().values(code=definition.code, **values))
        else:
            self.connection.execute(
                roles.update().where(roles.c.code == definition.code).values(**values)
            )

    def revoke_role_sessions(self, code: str, now: datetime) -> None:
        self.connection.execute(
            sessions.update()
            .where(
                sessions.c.user_id.in_(
                    select(user_roles.c.user_id).where(user_roles.c.role == code)
                ),
                sessions.c.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def list_users(self, offset: int, limit: int) -> list[User]:
        rows = (
            self.connection.execute(
                select(users).order_by(users.c.name, users.c.id).offset(offset).limit(limit)
            )
            .mappings()
            .all()
        )
        return [user for row in rows if (user := self._user(row)) is not None]

    def update_password_hash(self, user_id: UUID, hashed: str) -> None:
        self.connection.execute(
            users.update().where(users.c.id == user_id).values(password_hash=hashed)
        )

    def lock_role_changes(self) -> None:
        # Serialize admin membership changes, including the last-admin check.
        self.connection.execute(text("SELECT pg_advisory_xact_lock(71001)"))

    def admin_count(self) -> int:
        return int(
            self.connection.execute(
                select(func.count())
                .select_from(user_roles.join(users))
                .where(user_roles.c.role == Role.ADMIN.value, users.c.is_active.is_(True))
            ).scalar_one()
        )

    def add_session(self, session: Session) -> None:
        self.connection.execute(
            sessions.insert().values(
                id=session.id,
                user_id=session.user_id,
                token_hash=session.token_hash,
                created_at=session.created_at,
                expires_at=session.expires_at,
            )
        )

    def _session(self, row: RowMapping | None) -> Session | None:
        return Session(**row) if row is not None else None

    def session_for_token(self, token_hash: str) -> Session | None:
        return self._session(
            self.connection.execute(select(sessions).where(sessions.c.token_hash == token_hash))
            .mappings()
            .first()
        )

    def session_by_id(self, session_id: UUID) -> Session | None:
        return self._session(
            self.connection.execute(select(sessions).where(sessions.c.id == session_id))
            .mappings()
            .first()
        )

    def sessions_for_user(self, user_id: UUID, now: datetime) -> list[Session]:
        rows = self.connection.execute(
            select(sessions)
            .where(
                sessions.c.user_id == user_id,
                sessions.c.revoked_at.is_(None),
                sessions.c.expires_at > now,
            )
            .order_by(sessions.c.created_at.desc())
        ).mappings()
        return [Session(**row) for row in rows]

    def revoke_session(self, session_id: UUID, now: datetime) -> None:
        self.connection.execute(
            sessions.update()
            .where(sessions.c.id == session_id, sessions.c.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    def revoke_user_sessions(self, user_id: UUID, now: datetime) -> None:
        self.connection.execute(
            sessions.update()
            .where(sessions.c.user_id == user_id, sessions.c.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    def consume_rate(self, key: str, now: datetime, limit: int, seconds: int) -> bool:
        expired = rate_limits.c.started_at <= now - timedelta(seconds=seconds)
        query = insert(rate_limits).values(key=key, started_at=now, attempts=1)
        upsert = query.on_conflict_do_update(
            index_elements=[rate_limits.c.key],
            set_={
                "started_at": case((expired, now), else_=rate_limits.c.started_at),
                "attempts": case(
                    (expired, 1), else_=func.least(rate_limits.c.attempts + 1, limit + 1)
                ),
            },
        ).returning(rate_limits.c.attempts)
        return int(self.connection.execute(upsert).scalar_one()) <= limit

    def audit(
        self,
        action: str,
        actor_id: UUID | None,
        subject_id: UUID,
        now: datetime,
        details: dict[str, list[str]],
    ) -> None:
        self.connection.execute(
            audit.insert().values(
                id=uuid4(),
                actor_id=actor_id,
                subject_id=subject_id,
                action=action,
                created_at=now,
                details=details,
            )
        )


class PostgresIdentityUnitOfWork:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def __enter__(self) -> "PostgresIdentityUnitOfWork":
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.repository: IdentityRepository = PostgresIdentityRepository(self.connection)
        return self

    def commit(self) -> None:
        self.transaction.commit()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()
