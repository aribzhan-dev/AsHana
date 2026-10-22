"""Finance: expenses, bank commission, sales plans, owners and dividends, payroll."""

from alembic import op

revision = "0016_finance"
down_revision = "0015_outbox_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE inventory_directories DROP CONSTRAINT inventory_directories_kind_check;
        ALTER TABLE inventory_directories ADD CONSTRAINT inventory_directories_kind_check
            CHECK(kind IN ('supplier','warehouse','payment_method','category','expense_category'));
        -- Bank or acquirer fee per payment method, in basis points (1% = 100).
        ALTER TABLE inventory_directories ADD COLUMN commission_bp INTEGER NOT NULL DEFAULT 0
            CHECK(commission_bp BETWEEN 0 AND 10000);
        GRANT UPDATE (commission_bp) ON inventory_directories TO ashana_app;
        INSERT INTO inventory_directories (id, kind, name, name_key) VALUES
        ('00000000-0000-0000-0000-000000000004','payment_method','Онлайн-оплата','онлайн-оплата'),
        ('00000000-0000-0000-0000-000000000011','expense_category','Аренда','аренда'),
        ('00000000-0000-0000-0000-000000000012','expense_category','Коммунальные услуги',
         'коммунальные услуги'),
        ('00000000-0000-0000-0000-000000000013','expense_category','Налоги','налоги'),
        ('00000000-0000-0000-0000-000000000014','expense_category','Прочие расходы',
         'прочие расходы')
        ON CONFLICT DO NOTHING;

        CREATE TABLE finance_expenses (
            id UUID PRIMARY KEY,
            category_id UUID NOT NULL REFERENCES inventory_directories(id),
            -- Negative amounts are corrections; history is never rewritten.
            amount_minor BIGINT NOT NULL CHECK(amount_minor <> 0
                AND amount_minor BETWEEN -999999999999 AND 999999999999),
            payment_method_id UUID NOT NULL REFERENCES inventory_directories(id),
            spent_at TIMESTAMPTZ NOT NULL,
            note VARCHAR(200) NOT NULL,
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX ix_finance_expenses_spent ON finance_expenses(spent_at);

        CREATE TABLE finance_sales_plans (
            month DATE NOT NULL CHECK(extract(day FROM month) = 1),
            category VARCHAR(60) NOT NULL,
            target_minor BIGINT NOT NULL CHECK(target_minor BETWEEN 0 AND 999999999999),
            version INTEGER NOT NULL CHECK(version > 0),
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            updated_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (month, category)
        );

        CREATE TABLE finance_owners (
            id UUID PRIMARY KEY,
            name VARCHAR(100) NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 100),
            share_bp INTEGER NOT NULL CHECK(share_bp BETWEEN 1 AND 10000),
            active BOOLEAN NOT NULL,
            version INTEGER NOT NULL CHECK(version > 0),
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE TABLE finance_dividends (
            id UUID PRIMARY KEY,
            owner_id UUID NOT NULL REFERENCES finance_owners(id),
            month DATE NOT NULL CHECK(extract(day FROM month) = 1),
            amount_minor BIGINT NOT NULL CHECK(amount_minor BETWEEN 1 AND 999999999999),
            payment_method_id UUID NOT NULL REFERENCES inventory_directories(id),
            paid_at TIMESTAMPTZ NOT NULL,
            note VARCHAR(200) NOT NULL,
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            created_at TIMESTAMPTZ NOT NULL
        );

        CREATE TABLE payroll_workers (
            id UUID PRIMARY KEY,
            name VARCHAR(100) NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 100),
            position VARCHAR(100) NOT NULL,
            -- Optional link to a staff login: personal sales and self check-in.
            user_id UUID UNIQUE REFERENCES identity_users(id),
            active BOOLEAN NOT NULL,
            monthly_minor BIGINT NOT NULL CHECK(monthly_minor BETWEEN 0 AND 999999999999),
            daily_minor BIGINT NOT NULL CHECK(daily_minor BETWEEN 0 AND 999999999999),
            hourly_minor BIGINT NOT NULL CHECK(hourly_minor BETWEEN 0 AND 999999999999),
            sales_bp INTEGER NOT NULL CHECK(sales_bp BETWEEN 0 AND 10000),
            sales_base VARCHAR(10) NOT NULL CHECK(sales_base IN ('all','personal')),
            profit_bp INTEGER NOT NULL CHECK(profit_bp BETWEEN 0 AND 10000),
            profit_base VARCHAR(10) NOT NULL CHECK(profit_base IN ('simple','full')),
            version INTEGER NOT NULL CHECK(version > 0),
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
        CREATE TABLE payroll_shifts (
            id UUID PRIMARY KEY,
            worker_id UUID NOT NULL REFERENCES payroll_workers(id),
            starts_at TIMESTAMPTZ NOT NULL,
            ends_at TIMESTAMPTZ,
            source VARCHAR(10) NOT NULL CHECK(source IN ('self','manager')),
            note VARCHAR(200) NOT NULL,
            voided BOOLEAN NOT NULL DEFAULT false,
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CHECK(ends_at IS NULL
                OR (ends_at > starts_at AND ends_at <= starts_at + interval '24 hours'))
        );
        CREATE UNIQUE INDEX uq_payroll_open_shift ON payroll_shifts(worker_id)
            WHERE ends_at IS NULL AND NOT voided;
        CREATE INDEX ix_payroll_shifts_start ON payroll_shifts(starts_at);
        CREATE TABLE payroll_payments (
            id UUID PRIMARY KEY,
            worker_id UUID NOT NULL REFERENCES payroll_workers(id),
            month DATE NOT NULL CHECK(extract(day FROM month) = 1),
            kind VARCHAR(10) NOT NULL CHECK(kind IN ('advance','salary','bonus')),
            amount_minor BIGINT NOT NULL CHECK(amount_minor BETWEEN 1 AND 999999999999),
            payment_method_id UUID NOT NULL REFERENCES inventory_directories(id),
            paid_at TIMESTAMPTZ NOT NULL,
            note VARCHAR(200) NOT NULL,
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            created_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX ix_payroll_payments_month ON payroll_payments(month);

        REVOKE ALL ON finance_expenses, finance_dividends, payroll_payments,
            finance_sales_plans, finance_owners, payroll_workers, payroll_shifts FROM ashana_app;
        GRANT SELECT, INSERT ON finance_expenses, finance_dividends, payroll_payments
            TO ashana_app;
        GRANT SELECT, INSERT, UPDATE ON finance_sales_plans, finance_owners, payroll_workers
            TO ashana_app;
        GRANT SELECT, INSERT ON payroll_shifts TO ashana_app;
        GRANT UPDATE (ends_at, voided, note, updated_at) ON payroll_shifts TO ashana_app;

        UPDATE identity_roles SET permissions = permissions || '["finance.manage"]'::jsonb,
            version = version + 1
        WHERE code = 'manager' AND NOT permissions @> '["finance.manage"]'::jsonb;
    """)


def downgrade() -> None:
    raise RuntimeError("Финансовая история требует отдельного плана отката")
