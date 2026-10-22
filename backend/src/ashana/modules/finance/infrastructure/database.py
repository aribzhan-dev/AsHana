from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from types import TracebackType
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from ashana.modules.finance.domain.models import (
    Money,
    Owner,
    Plan,
    ProfitAndLoss,
    Shift,
    Worker,
    month_bounds,
)
from ashana.modules.inventory.application.ports import InventoryRepository
from ashana.modules.inventory.domain.models import InventoryError

# Unit cost of every batch: purchase cost / received quantity; cooked batches take the
# cost of the raw batches they consumed divided by the actual yield.
UNIT_COST = """
initial AS (
  SELECT batch_id, sum(delta) AS qty FROM inventory_movements
  WHERE action IN ('receipt', 'production_output') GROUP BY batch_id
), raw_cost AS (
  SELECT b.id, b.total_cost_minor::numeric / NULLIF(i.qty, 0) AS unit_cost
  FROM inventory_batches b JOIN initial i ON i.batch_id = b.id
), prod_cost AS (
  SELECT p.id, sum(-m.delta * COALESCE(rc.unit_cost, 0)) / p.actual_yield AS unit_cost
  FROM production_batches p JOIN production_consumption c ON c.production_id = p.id
  JOIN inventory_movements m ON m.id = c.movement_id
  LEFT JOIN raw_cost rc ON rc.id = c.batch_id
  GROUP BY p.id, p.actual_yield
), unit_cost AS (
  SELECT r.id, COALESCE(pc.unit_cost, r.unit_cost, 0) AS unit_cost
  FROM raw_cost r LEFT JOIN prod_cost pc ON pc.id = r.id
)
"""

PNL = (
    "WITH "
    + UNIT_COST
    + """
SELECT
  (SELECT COALESCE(sum(d.total_minor), 0) FROM order_events e
     JOIN checkout_drafts d ON d.id = e.subject_id
     WHERE e.kind = 'confirmed' AND e.created_at >= :start AND e.created_at < :end)
  + (SELECT COALESCE(sum(total_minor), 0) FROM pos_attempts
     WHERE outcome = 'success' AND created_at >= :start AND created_at < :end) AS revenue,
  (SELECT COALESCE(sum(d.total_minor), 0) FROM order_events e
     JOIN checkout_drafts d ON d.id = e.subject_id
     WHERE e.kind = 'paid_cancelled' AND e.created_at >= :start AND e.created_at < :end)
  + (SELECT COALESCE(sum(amount_minor), 0) FROM pos_returns
     WHERE created_at >= :start AND created_at < :end) AS returns,
  (SELECT COALESCE(round(sum(-m.delta * u.unit_cost)), 0) FROM inventory_movements m
     JOIN unit_cost u ON u.id = m.batch_id
     WHERE m.action IN ('mock_pos_sale', 'mock_fulfil', 'pos_return')
       AND m.created_at >= :start AND m.created_at < :end) AS cost_of_goods,
  (SELECT COALESCE(round(sum(-m.delta * u.unit_cost)), 0) FROM inventory_movements m
     JOIN unit_cost u ON u.id = m.batch_id
     WHERE m.action IN ('write_off', 'count')
       AND m.created_at >= :start AND m.created_at < :end) AS writeoffs,
  (SELECT COALESCE(sum(expenses_minor), 0) FROM inventory_invoices
     WHERE received_at >= :start AND received_at < :end) AS invoice_expenses
"""
)

SALES_BY_METHOD = """
SELECT d.id::text AS id, d.name, d.commission_bp, COALESCE(sum(s.amount), 0) AS amount
FROM inventory_directories d
LEFT JOIN (
  SELECT payment_method_id AS method, total_minor AS amount FROM pos_attempts
  WHERE outcome = 'success' AND payment_method_id IS NOT NULL
    AND created_at >= :start AND created_at < :end
  UNION ALL
  SELECT '00000000-0000-0000-0000-000000000004'::uuid, dr.total_minor
  FROM order_events e JOIN checkout_drafts dr ON dr.id = e.subject_id
  WHERE e.kind = 'confirmed' AND e.created_at >= :start AND e.created_at < :end
) s ON s.method = d.id
WHERE d.kind = 'payment_method'
GROUP BY d.id, d.name, d.commission_bp
ORDER BY d.name, d.id
"""

WORKER_COLUMNS = """w.id, w.name, w.position, w.user_id, w.active, w.monthly_minor,
  w.daily_minor, w.hourly_minor, w.sales_bp, w.sales_base, w.profit_bp, w.profit_base,
  w.version, w.created_at, w.updated_at,
  COALESCE(NULLIF(u.nickname, ''), u.name, '') AS user_name"""


class PostgresFinanceRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def _rows(self, sql: str, **params: object) -> list[dict[str, Any]]:
        return [dict(r) for r in self.connection.execute(text(sql), params).mappings()]

    # --- profit and loss -------------------------------------------------------------
    def profit_and_loss(self, month: date) -> ProfitAndLoss:
        start, end = month_bounds(month)
        row = self.connection.execute(text(PNL), {"start": start, "end": end}).mappings().one()
        pnl = ProfitAndLoss(
            month,
            revenue=int(row["revenue"]),
            returns=int(row["returns"]),
            cost_of_goods=int(row["cost_of_goods"]),
            writeoffs=int(row["writeoffs"]),
            invoice_expenses=int(row["invoice_expenses"]),
        )
        for r in self._rows(
            """SELECT d.name, sum(e.amount_minor) AS amount FROM finance_expenses e
               JOIN inventory_directories d ON d.id = e.category_id
               WHERE e.spent_at >= :start AND e.spent_at < :end GROUP BY d.name ORDER BY d.name""",
            start=start,
            end=end,
        ):
            pnl.expenses[str(r["name"])] = int(r["amount"])
        pnl.sales_by_method = [
            {**r, "amount": int(r["amount"]), "commission_bp": int(r["commission_bp"])}
            for r in self._rows(SALES_BY_METHOD, start=start, end=end)
        ]
        return pnl

    def personal_sales(self, user_id: UUID, month: date) -> int:
        start, end = month_bounds(month)
        row = self.connection.execute(
            text(
                """SELECT
                 (SELECT COALESCE(sum(total_minor), 0) FROM pos_attempts
                  WHERE outcome = 'success' AND actor_id = :user
                    AND created_at >= :start AND created_at < :end)
                 - (SELECT COALESCE(sum(r.amount_minor), 0) FROM pos_returns r
                    JOIN pos_attempts p ON p.id = r.sale_id
                    WHERE p.actor_id = :user AND r.created_at >= :start AND r.created_at < :end)"""
            ),
            {"user": user_id, "start": start, "end": end},
        ).scalar_one()
        return int(row)

    def category_sales(self, month: date) -> dict[str, int]:
        start, end = month_bounds(month)
        rows = self._rows(
            """WITH lines AS (
                 SELECT p.lines FROM pos_attempts p WHERE p.outcome = 'success'
                   AND p.created_at >= :start AND p.created_at < :end
                 UNION ALL
                 SELECT d.lines FROM order_events e JOIN checkout_drafts d ON d.id = e.subject_id
                 WHERE e.kind = 'confirmed' AND e.created_at >= :start AND e.created_at < :end
               )
               SELECT COALESCE(NULLIF(i.category, ''), 'Без категории') AS category,
                 sum((line->>'quantity')::bigint * (line->>'price_minor')::bigint) AS amount
               FROM lines CROSS JOIN LATERAL jsonb_array_elements(lines.lines) line
               JOIN inventory_items i ON i.id = (line->>'item_id')::uuid
               GROUP BY 1""",
            start=start,
            end=end,
        )
        return {str(r["category"]): int(r["amount"]) for r in rows}

    def daily_sales(self, month: date) -> dict[int, int]:
        start, end = month_bounds(month)
        rows = self._rows(
            """SELECT extract(day FROM at AT TIME ZONE 'Asia/Almaty')::int AS day,
                 sum(amount) AS amount FROM (
                 SELECT created_at AS at, total_minor AS amount FROM pos_attempts
                 WHERE outcome = 'success' AND created_at >= :start AND created_at < :end
                 UNION ALL
                 SELECT e.created_at, d.total_minor FROM order_events e
                 JOIN checkout_drafts d ON d.id = e.subject_id
                 WHERE e.kind = 'confirmed' AND e.created_at >= :start AND e.created_at < :end
               ) s GROUP BY 1""",
            start=start,
            end=end,
        )
        return {int(r["day"]): int(r["amount"]) for r in rows}

    # --- payment method commission ----------------------------------------------------
    def set_commission(self, method_id: UUID, basis_points: int) -> bool:
        result = self.connection.execute(
            text(
                "UPDATE inventory_directories SET commission_bp = :bp "
                "WHERE id = :id AND kind = 'payment_method'"
            ),
            {"bp": basis_points, "id": method_id},
        )
        return result.rowcount == 1

    def directory_name(self, id: UUID, kind: str) -> str | None:
        value = self.connection.execute(
            text("SELECT name FROM inventory_directories WHERE id = :id AND kind = :kind"),
            {"id": id, "kind": kind},
        ).scalar_one_or_none()
        return str(value) if value is not None else None

    # --- expenses, dividends, salary payments (append-only money) ----------------------
    def add_expense(self, m: Money) -> None:
        self.connection.execute(
            text(
                "INSERT INTO finance_expenses VALUES "
                "(:id, :subject_id, :amount_minor, :payment_method_id, :at, :note, :actor_id,"
                " :created_at)"
            ),
            asdict(m),
        )

    def expenses(self, month: date) -> list[Money]:
        start, end = month_bounds(month)
        return [
            Money(**r)
            for r in self._rows(
                """SELECT e.id, e.category_id AS subject_id, e.amount_minor, e.payment_method_id,
                     e.spent_at AS at, e.note, e.actor_id, e.created_at,
                     c.name AS subject_name, p.name AS method_name
                   FROM finance_expenses e
                   JOIN inventory_directories c ON c.id = e.category_id
                   JOIN inventory_directories p ON p.id = e.payment_method_id
                   WHERE e.spent_at >= :start AND e.spent_at < :end
                   ORDER BY e.spent_at DESC, e.id""",
                start=start,
                end=end,
            )
        ]

    def add_dividend(self, m: Money) -> None:
        self.connection.execute(
            text(
                "INSERT INTO finance_dividends VALUES (:id, :subject_id, :month, :amount_minor,"
                " :payment_method_id, :at, :note, :actor_id, :created_at)"
            ),
            asdict(m),
        )

    def dividends(self, month: date) -> list[Money]:
        return [
            Money(**r)
            for r in self._rows(
                """SELECT d.id, d.owner_id AS subject_id, d.amount_minor, d.payment_method_id,
                     d.paid_at AS at, d.note, d.actor_id, d.created_at, d.month,
                     o.name AS subject_name, p.name AS method_name
                   FROM finance_dividends d JOIN finance_owners o ON o.id = d.owner_id
                   JOIN inventory_directories p ON p.id = d.payment_method_id
                   WHERE d.month = :month ORDER BY d.paid_at DESC, d.id""",
                month=month,
            )
        ]

    def add_salary_payment(self, m: Money) -> None:
        self.connection.execute(
            text(
                "INSERT INTO payroll_payments VALUES (:id, :subject_id, :month, :kind,"
                " :amount_minor, :payment_method_id, :at, :note, :actor_id, :created_at)"
            ),
            asdict(m),
        )

    def salary_payments(self, month: date, worker_id: UUID | None = None) -> list[Money]:
        return [
            Money(**r)
            for r in self._rows(
                """SELECT y.id, y.worker_id AS subject_id, y.amount_minor, y.payment_method_id,
                     y.paid_at AS at, y.note, y.actor_id, y.created_at, y.month, y.kind,
                     w.name AS subject_name, p.name AS method_name
                   FROM payroll_payments y JOIN payroll_workers w ON w.id = y.worker_id
                   JOIN inventory_directories p ON p.id = y.payment_method_id
                   WHERE y.month = :month
                     AND (CAST(:worker AS uuid) IS NULL OR y.worker_id = CAST(:worker AS uuid))
                   ORDER BY y.paid_at DESC, y.id""",
                month=month,
                worker=worker_id,
            )
        ]

    def lock(self, key: str) -> None:
        self.connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    # --- owners and plans ---------------------------------------------------------------
    def owners(self) -> list[Owner]:
        return [
            Owner(**r)
            for r in self._rows(
                "SELECT id, name, share_bp, active, version, created_at FROM finance_owners "
                "ORDER BY created_at, id"
            )
        ]

    def save_owner(self, owner: Owner, *, new: bool) -> None:
        if new:
            self.connection.execute(
                text(
                    "INSERT INTO finance_owners VALUES"
                    " (:id, :name, :share_bp, :active, :version, :created_at)"
                ),
                asdict(owner),
            )
        else:
            self.connection.execute(
                text(
                    "UPDATE finance_owners SET name = :name, share_bp = :share_bp,"
                    " active = :active, version = :version WHERE id = :id"
                ),
                asdict(owner),
            )

    def plans(self, month: date) -> list[Plan]:
        return [
            Plan(**r)
            for r in self._rows(
                "SELECT month, category, target_minor, version FROM finance_sales_plans "
                "WHERE month = :month ORDER BY category",
                month=month,
            )
        ]

    def save_plan(self, plan: Plan, actor: UUID, now: datetime) -> None:
        self.connection.execute(
            text(
                """INSERT INTO finance_sales_plans VALUES
                     (:month, :category, :target_minor, :version, :actor, :now)
                   ON CONFLICT (month, category) DO UPDATE SET target_minor = :target_minor,
                     version = :version, actor_id = :actor, updated_at = :now"""
            ),
            {**asdict(plan), "actor": actor, "now": now},
        )

    # --- payroll workers and shifts ---------------------------------------------------------
    def workers(self, *, active_only: bool = False) -> list[Worker]:
        return [
            Worker(**r)
            for r in self._rows(
                f"SELECT {WORKER_COLUMNS} FROM payroll_workers w "
                "LEFT JOIN identity_users u ON u.id = w.user_id "
                f"{'WHERE w.active' if active_only else ''} ORDER BY w.name, w.id"
            )
        ]

    def worker(self, id: UUID, *, lock: bool = False) -> Worker | None:
        rows = self._rows(
            f"SELECT {WORKER_COLUMNS} FROM payroll_workers w "
            "LEFT JOIN identity_users u ON u.id = w.user_id WHERE w.id = :id"
            + (" FOR UPDATE OF w" if lock else ""),
            id=id,
        )
        return Worker(**rows[0]) if rows else None

    def worker_for_user(self, user_id: UUID) -> Worker | None:
        rows = self._rows("SELECT id FROM payroll_workers WHERE user_id = :u AND active", u=user_id)
        return self.worker(rows[0]["id"], lock=True) if rows else None

    def save_worker(self, worker: Worker, *, new: bool) -> None:
        values = asdict(worker)
        values.pop("user_name")
        try:
            if new:
                self.connection.execute(
                    text(
                        "INSERT INTO payroll_workers VALUES (:id, :name, :position, :user_id,"
                        " :active, :monthly_minor, :daily_minor, :hourly_minor, :sales_bp,"
                        " :sales_base, :profit_bp, :profit_base, :version, :created_at,"
                        " :updated_at)"
                    ),
                    values,
                )
            else:
                self.connection.execute(
                    text(
                        "UPDATE payroll_workers SET name = :name, position = :position,"
                        " user_id = :user_id, active = :active, monthly_minor = :monthly_minor,"
                        " daily_minor = :daily_minor, hourly_minor = :hourly_minor,"
                        " sales_bp = :sales_bp, sales_base = :sales_base,"
                        " profit_bp = :profit_bp, profit_base = :profit_base,"
                        " version = :version, updated_at = :updated_at WHERE id = :id"
                    ),
                    values,
                )
        except IntegrityError:
            raise InventoryError(
                "WORKER_LINKED",
                "Этот аккаунт уже привязан к другому сотруднику",
                {"user_id": ["Этот аккаунт уже привязан к другому сотруднику"]},
            ) from None

    def shifts(self, month: date, worker_id: UUID | None = None) -> list[Shift]:
        start, end = month_bounds(month)
        return [
            Shift(**r)
            for r in self._rows(
                """SELECT id, worker_id, starts_at, ends_at, source, note, voided, actor_id,
                     created_at, updated_at FROM payroll_shifts
                   WHERE starts_at >= :start AND starts_at < :end
                     AND (CAST(:worker AS uuid) IS NULL OR worker_id = CAST(:worker AS uuid))
                   ORDER BY starts_at DESC, id""",
                start=start,
                end=end,
                worker=worker_id,
            )
        ]

    def open_shift(self, worker_id: UUID) -> Shift | None:
        rows = self._rows(
            """SELECT id, worker_id, starts_at, ends_at, source, note, voided, actor_id,
                 created_at, updated_at FROM payroll_shifts
               WHERE worker_id = :w AND ends_at IS NULL AND NOT voided""",
            w=worker_id,
        )
        return Shift(**rows[0]) if rows else None

    def shift(self, id: UUID) -> Shift | None:
        rows = self._rows(
            """SELECT id, worker_id, starts_at, ends_at, source, note, voided, actor_id,
                 created_at, updated_at FROM payroll_shifts WHERE id = :id""",
            id=id,
        )
        return Shift(**rows[0]) if rows else None

    def add_shift(self, shift: Shift) -> None:
        try:
            self.connection.execute(
                text(
                    "INSERT INTO payroll_shifts VALUES (:id, :worker_id, :starts_at, :ends_at,"
                    " :source, :note, :voided, :actor_id, :created_at, :updated_at)"
                ),
                asdict(shift),
            )
        except IntegrityError:
            raise InventoryError("SHIFT_OPEN", "Смена уже начата") from None

    def update_shift(self, shift: Shift) -> None:
        self.connection.execute(
            text(
                "UPDATE payroll_shifts SET ends_at = :ends_at, voided = :voided, note = :note,"
                " updated_at = :updated_at WHERE id = :id"
            ),
            asdict(shift),
        )

    def staff(self) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT id::text AS id, COALESCE(NULLIF(nickname, ''), name) AS name, login"
            " FROM identity_users WHERE is_active ORDER BY name, id"
        )


def hours(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


class PostgresFinanceUnitOfWork:
    def __init__(
        self,
        engine: Engine,
        authorize: Callable[[Connection, str, str | None], tuple[UUID, frozenset[str]]],
        stock: Callable[[Connection], InventoryRepository],
    ) -> None:
        self.engine, self.authorizer, self.stock_factory = engine, authorize, stock

    def __enter__(self) -> "PostgresFinanceUnitOfWork":
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.repository = PostgresFinanceRepository(self.connection)
        self.stock = self.stock_factory(self.connection)
        return self

    def authorize(self, token: str, permission: str | None = "finance.manage") -> UUID:
        self.connection.execute(text("SELECT pg_advisory_xact_lock_shared(71001)"))
        return self.authorizer(self.connection, token, permission)[0]

    def commit(self) -> None:
        self.transaction.commit()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if self.transaction.is_active:
                self.transaction.rollback()
        finally:
            self.connection.close()
