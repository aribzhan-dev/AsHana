"""Separate staff credentials from optional contact information without losing accounts."""

import sqlalchemy as sa
from alembic import op

revision = "0003_staff_login"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("identity_users", sa.Column("login", sa.String(40), nullable=True))
    # UUID-derived logins are deterministic and unique; existing passwords and sessions survive.
    op.execute("UPDATE identity_users SET login = 'staff_' || replace(id::text, '-', '')")
    op.alter_column("identity_users", "login", nullable=False)
    op.create_unique_constraint("identity_users_login_key", "identity_users", ["login"])
    op.create_check_constraint(
        "ck_identity_login", "identity_users", "login ~ '^[a-z][a-z0-9._-]{2,39}$'"
    )
    op.alter_column("identity_users", "phone", nullable=True)
    op.drop_constraint("identity_users_phone_key", "identity_users", type_="unique")


def downgrade() -> None:
    raise RuntimeError("Откат логинов требует отдельного плана сохранения доступа сотрудников")
