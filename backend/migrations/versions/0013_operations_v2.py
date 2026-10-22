"""Category directory, dining options, permanent goods, POS returns and supplier debts."""

from alembic import op

revision = "0013_operations_v2"
down_revision = "0012_product_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One shared category list replaces free-text spellings ("Вода" vs "вода").
    op.execute("""
        ALTER TABLE inventory_directories DROP CONSTRAINT inventory_directories_kind_check;
        ALTER TABLE inventory_directories ADD CONSTRAINT inventory_directories_kind_check
            CHECK(kind IN ('supplier','warehouse','payment_method','category'));
        INSERT INTO inventory_directories (id, kind, name, name_key)
        SELECT gen_random_uuid(), 'category', min(name), key FROM (
            SELECT left(trim(category), 60) AS name, lower(left(trim(category), 60)) AS key
            FROM inventory_items WHERE trim(category) <> ''
            UNION ALL
            SELECT trim(category), lower(trim(category))
            FROM catalog_entries WHERE trim(category) <> ''
        ) found GROUP BY key;
    """)

    # Takeaway or eat-in choice travels with the checkout and the paid order.
    op.execute("""
        ALTER TABLE checkout_drafts ADD COLUMN dining VARCHAR(10) NOT NULL DEFAULT 'here',
            ADD CONSTRAINT ck_order_dining CHECK(dining IN ('here','takeaway'));
    """)
    # Bought-in goods that stay on sale in every period while stock lasts.
    op.execute("""
        ALTER TABLE inventory_items ADD COLUMN always_on_menu BOOLEAN NOT NULL DEFAULT false,
            ADD CONSTRAINT ck_item_always_on_menu CHECK(NOT always_on_menu OR kind = 'purchased');
        GRANT UPDATE (always_on_menu) ON inventory_items TO ashana_app;
    """)

    # Counter returns: append-only, refunded with the sale's mock payment method.
    op.execute("""
        CREATE TABLE pos_returns (
            id UUID PRIMARY KEY,
            sale_id UUID NOT NULL REFERENCES pos_attempts(id),
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            created_at TIMESTAMPTZ NOT NULL,
            reason VARCHAR(200) NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 200),
            disposition VARCHAR(10) NOT NULL CHECK(disposition IN ('restock','write_off')),
            amount_minor BIGINT NOT NULL CHECK(amount_minor BETWEEN 0 AND 99999999999900),
            lines JSONB NOT NULL CHECK(jsonb_typeof(lines) = 'array'
                AND jsonb_array_length(lines) BETWEEN 1 AND 100)
        );
        CREATE INDEX ix_pos_returns_sale ON pos_returns(sale_id);
        CREATE INDEX ix_pos_returns_created ON pos_returns(created_at);
        REVOKE ALL ON pos_returns FROM ashana_app;
        GRANT SELECT, INSERT ON pos_returns TO ashana_app;
        ALTER TABLE inventory_movements DROP CONSTRAINT ck_inventory_movement_action;
        ALTER TABLE inventory_movements ADD CONSTRAINT ck_inventory_movement_action CHECK(
            action IN ('receipt','write_off','count','suspend','resume','production_consume',
                       'production_output','mock_fulfil','mock_pos_sale','pos_return'));
        UPDATE identity_roles SET permissions = permissions || '["pos.refund"]'::jsonb,
            version = version + 1
        WHERE code = 'manager' AND NOT permissions @> '["pos.refund"]'::jsonb;
    """)
    # Supplier debts: what was paid on receipt plus later payments; the rest is owed.
    op.execute("""
        ALTER TABLE inventory_invoices ADD COLUMN paid_on_receipt_minor BIGINT;
        UPDATE inventory_invoices SET paid_on_receipt_minor = total_minor;
        ALTER TABLE inventory_invoices ALTER COLUMN paid_on_receipt_minor SET NOT NULL,
            ADD CONSTRAINT ck_invoice_paid CHECK(
                paid_on_receipt_minor BETWEEN 0 AND total_minor);
        CREATE TABLE inventory_invoice_payments (
            id UUID PRIMARY KEY,
            invoice_id UUID NOT NULL REFERENCES inventory_invoices(id),
            amount_minor BIGINT NOT NULL CHECK(amount_minor BETWEEN 1 AND 999999999999),
            payment_method_id UUID NOT NULL REFERENCES inventory_directories(id),
            note VARCHAR(200) NOT NULL,
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            paid_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX ix_invoice_payments_invoice ON inventory_invoice_payments(invoice_id);
        REVOKE ALL ON inventory_invoice_payments FROM ashana_app;
        GRANT SELECT, INSERT ON inventory_invoice_payments TO ashana_app;
    """)


def downgrade() -> None:
    raise RuntimeError("Новые операции требуют отдельного плана отката")
