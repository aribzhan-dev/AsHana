"""Product defaults and staff display nicknames."""

from alembic import op

revision = "0012_product_profiles"
down_revision = "0011_receiving"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE identity_users ADD COLUMN nickname VARCHAR(100) NOT NULL DEFAULT '';
        ALTER TABLE inventory_items
            ADD COLUMN category VARCHAR(100) NOT NULL DEFAULT '',
            ADD COLUMN purchase_price_minor BIGINT NOT NULL DEFAULT 0
                CHECK(purchase_price_minor BETWEEN 0 AND 999999999999),
            ADD COLUMN sale_price_minor BIGINT NOT NULL DEFAULT 0
                CHECK(sale_price_minor BETWEEN 0 AND 999999999999),
            ADD COLUMN version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0);
        GRANT UPDATE (nickname) ON identity_users TO ashana_app;
        GRANT UPDATE (name, name_key, category, purchase_price_minor, sale_price_minor, version)
            ON inventory_items TO ashana_app;
    """)


def downgrade() -> None:
    raise RuntimeError("Сохранённые карточки требуют отдельного плана отката")
