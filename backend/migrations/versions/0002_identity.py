"""Add staff identities, revocable sessions, role audit and persistent rate limits."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_identity"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("phone", sa.String(12), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("phone ~ '^\\+7[0-9]{10}$'", name="ck_identity_phone"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="ck_identity_name"),
    )
    role_table = op.create_table(
        "identity_roles", sa.Column("code", sa.String(20), primary_key=True)
    )
    op.bulk_insert(
        role_table,
        [{"code": name} for name in ("kitchen", "cashier", "storekeeper", "manager", "admin")],
    )
    op.create_table(
        "identity_user_roles",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("identity_users.id"), primary_key=True),
        sa.Column("role", sa.String(20), sa.ForeignKey("identity_roles.code"), primary_key=True),
    )
    op.create_table(
        "identity_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("identity_users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("expires_at > created_at", name="ck_identity_session_expiry"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_identity_token_hash"),
    )
    op.create_index("ix_identity_sessions_user", "identity_sessions", ["user_id"])
    op.create_table(
        "identity_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("identity_users.id")),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "identity_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempts > 0", name="ck_identity_attempts"),
    )
    op.execute("REVOKE UPDATE, DELETE ON identity_audit FROM ashana_app")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON identity_roles FROM ashana_app")


def downgrade() -> None:
    raise RuntimeError("Откат identity требует отдельного согласования сохранности данных")
