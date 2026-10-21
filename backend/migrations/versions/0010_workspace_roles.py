"""Persist editable staff permissions while retaining the administrator recovery role."""

import json

import sqlalchemy as sa
from alembic import op

revision = "0010_workspace_roles"
down_revision = "0009_pos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE identity_roles ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT '', "
        "ADD COLUMN permissions JSONB NOT NULL DEFAULT '[]', "
        "ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
    )
    defaults = {
        "admin": ("Администратор", ["identity.manage"]),
        "manager": (
            "Управляющий",
            [
                "kitchen.read",
                "kitchen.manage",
                "production.manage",
                "orders.fulfil",
                "pos.sell",
                "inventory.manage",
                "catalog.manage",
                "reporting.read",
            ],
        ),
        "cashier": ("Кассир", ["kitchen.read", "orders.fulfil", "pos.sell"]),
        "kitchen": ("Кухня", ["kitchen.read", "kitchen.manage", "production.manage"]),
        "storekeeper": ("Кладовщик", ["inventory.manage"]),
    }
    for code, (name, permissions) in defaults.items():
        op.get_bind().execute(
            sa.text(
                "UPDATE identity_roles SET name=:name, permissions=CAST(:permissions AS jsonb) "
                "WHERE code=:code"
            ),
            {"code": code, "name": name, "permissions": json.dumps(permissions)},
        )
    op.execute("""
        ALTER TABLE identity_roles
        ADD CONSTRAINT ck_role_version CHECK (version > 0),
        ADD CONSTRAINT ck_role_name CHECK (length(trim(name)) BETWEEN 1 AND 100),
        ADD CONSTRAINT ck_role_code CHECK (code ~ '^[a-z][a-z0-9_]{2,19}$'),
        ADD CONSTRAINT ck_role_permissions CHECK (jsonb_typeof(permissions) = 'array'),
        ADD CONSTRAINT ck_role_admin CHECK (
            code <> 'admin' OR permissions @> '["identity.manage"]'::jsonb)
    """)
    op.execute("ALTER TABLE catalog_entries ADD COLUMN category VARCHAR(60) NOT NULL DEFAULT ''")
    op.execute("GRANT INSERT, UPDATE ON identity_roles TO ashana_app")


def downgrade() -> None:
    raise RuntimeError("Откат ролей требует сохранения назначенных прав")
