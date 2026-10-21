"""Add meal periods, menu entries and immutable change audit."""

from alembic import op

revision = "0006_catalog"
down_revision = "0005_production"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE catalog_audit (
        id UUID NOT NULL,
        actor_id UUID NOT NULL,
        entity VARCHAR(20) NOT NULL,
        subject_id UUID NOT NULL,
        before JSONB,
        after JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_catalog_audit_entity CHECK (entity IN ('period','entry')),
        FOREIGN KEY(actor_id) REFERENCES identity_users (id)
        )
    """)
    op.execute("""
        CREATE INDEX ix_catalog_audit_subject_id ON catalog_audit (subject_id)
    """)
    op.execute("""
        CREATE TABLE catalog_periods (
        id UUID NOT NULL,
        name VARCHAR(100) NOT NULL,
        starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
        ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
        published BOOLEAN NOT NULL,
        version INTEGER NOT NULL,
        actor_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_catalog_period_window CHECK (ends_at > starts_at AND
        ends_at <= starts_at + interval '24 hours'),
        CONSTRAINT ck_catalog_period_values CHECK (version > 0 AND
        char_length(name) BETWEEN 1 AND
        100),
        FOREIGN KEY(actor_id) REFERENCES identity_users (id)
        )
    """)
    op.execute("""
        CREATE INDEX ix_catalog_periods_starts_at ON catalog_periods (starts_at)
    """)
    op.execute("""
        CREATE TABLE catalog_entries (
        id UUID NOT NULL,
        period_id UUID NOT NULL,
        item_id UUID NOT NULL,
        description VARCHAR(1000) NOT NULL,
        portion_label VARCHAR(100) NOT NULL,
        price_minor BIGINT NOT NULL,
        published BOOLEAN NOT NULL,
        version INTEGER NOT NULL,
        actor_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_catalog_period_item UNIQUE (period_id, item_id),
        CONSTRAINT ck_catalog_entry_values CHECK (price_minor BETWEEN 0 AND
        999999999999 AND
        version > 0),
        CONSTRAINT ck_catalog_portion CHECK (char_length(portion_label) BETWEEN 1 AND
        100),
        FOREIGN KEY(period_id) REFERENCES catalog_periods (id),
        FOREIGN KEY(item_id) REFERENCES inventory_items (id),
        FOREIGN KEY(actor_id) REFERENCES identity_users (id)
        )
    """)
    op.execute("""
        REVOKE DELETE ON catalog_periods, catalog_entries FROM ashana_app
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON catalog_audit FROM ashana_app
    """)


def downgrade() -> None:
    raise RuntimeError("Откат каталога требует плана сохранения меню и аудита")
