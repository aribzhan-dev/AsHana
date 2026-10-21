"""Invoices, purchasing directories and optional goods barcodes."""

from alembic import op

revision = "0011_receiving"
down_revision = "0010_workspace_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE inventory_directories (
            id UUID PRIMARY KEY, kind VARCHAR(20) NOT NULL,
            name VARCHAR(100) NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 100),
            name_key VARCHAR(200) NOT NULL,
            CHECK(kind IN ('supplier','warehouse','payment_method')),
            UNIQUE(kind, name_key)
        );
        INSERT INTO inventory_directories VALUES
        ('00000000-0000-0000-0000-000000000001','warehouse','Основной склад','основной склад'),
        ('00000000-0000-0000-0000-000000000002','payment_method','Наличные','наличные'),
        ('00000000-0000-0000-0000-000000000003','payment_method','Карта','карта');
        ALTER TABLE inventory_items ADD COLUMN barcode VARCHAR(14) UNIQUE,
        ADD CONSTRAINT ck_item_barcode CHECK(barcode IS NULL OR
            (kind='purchased' AND barcode ~ '^[0-9]{8,14}$'));
        ALTER TABLE inventory_batches ADD COLUMN warehouse_id UUID NOT NULL
            DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES inventory_directories(id);
        CREATE TABLE inventory_invoices (
            id UUID PRIMARY KEY, number VARCHAR(100) NOT NULL CHECK(length(trim(number)) > 0),
            supplier_id UUID NOT NULL REFERENCES inventory_directories(id),
            warehouse_id UUID NOT NULL REFERENCES inventory_directories(id),
            payment_method_id UUID NOT NULL REFERENCES inventory_directories(id),
            received_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            goods_minor BIGINT NOT NULL CHECK(goods_minor >= 0),
            expenses_minor BIGINT NOT NULL CHECK(expenses_minor >= 0),
            total_minor BIGINT NOT NULL CHECK(total_minor BETWEEN 0 AND 999999999999),
            note VARCHAR(200) NOT NULL,
            lines JSONB NOT NULL CHECK(jsonb_typeof(lines)='array'
                AND jsonb_array_length(lines) BETWEEN 1 AND 100),
            supplier_name VARCHAR(100) NOT NULL, warehouse_name VARCHAR(100) NOT NULL,
            payment_method_name VARCHAR(100) NOT NULL,
            CHECK(total_minor = goods_minor + expenses_minor),
            CHECK(received_at <= created_at), UNIQUE(supplier_id, number)
        );
        CREATE INDEX ix_invoice_date ON inventory_invoices(created_at DESC, id);
        GRANT UPDATE (barcode) ON inventory_items TO ashana_app;
        REVOKE ALL ON inventory_directories, inventory_invoices FROM ashana_app;
        GRANT SELECT, INSERT ON inventory_directories, inventory_invoices TO ashana_app;
        UPDATE identity_roles SET permissions = permissions || '["inventory.writeoff"]'::jsonb,
            version = version + 1 WHERE code IN ('manager','cashier')
            AND NOT permissions @> '["inventory.writeoff"]'::jsonb;
        ALTER TABLE pos_attempts ADD COLUMN payment_method_id UUID
            REFERENCES inventory_directories(id),
            ADD COLUMN payment_method_name VARCHAR(100) NOT NULL DEFAULT '';
    """)


def downgrade() -> None:
    raise RuntimeError("Накладные и движения сохраняются; откат требует отдельного плана")
