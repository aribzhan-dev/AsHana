from collections.abc import Callable
from dataclasses import replace
from types import TracebackType

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ashana.modules.reporting.application.ports import ReportRepository
from ashana.modules.reporting.domain.models import (
    COLUMNS,
    Dashboard,
    Report,
    ReportFilter,
    ReportKind,
)

# Explicit read projections: reporting never imports or mutates another module's ORM tables.
SALES_BASE = """
WITH events AS (
    SELECT d.lines, e.kind, e.created_at, COALESCE(o.mode, 'mock') AS mode,
           'online' AS channel, s.period_id
    FROM order_events e JOIN checkout_drafts d ON d.id=e.subject_id
    JOIN order_slots s ON s.id=d.slot_id LEFT JOIN orders o ON o.id=d.id
    WHERE e.kind IN ('confirmed','completed','paid_cancelled','cancelled','expired')
    UNION ALL
    SELECT p.lines, 'pos', p.created_at, p.mode, 'cashier', NULL::uuid
    FROM pos_attempts p WHERE p.outcome='success'
    UNION ALL
    SELECT r.lines, 'pos_return', r.created_at, 'mock', 'cashier', NULL::uuid
    FROM pos_returns r
), expanded AS (
    SELECT (line->>'item_id')::uuid AS item_id, line->>'name' AS name,
           line->>'unit' AS unit, (line->>'quantity')::bigint AS quantity,
           (line->>'price_minor')::bigint AS price, e.kind, e.channel,
           COALESCE(e.period_id, ce.period_id) AS period_id
    FROM events e CROSS JOIN LATERAL jsonb_array_elements(e.lines) line
    LEFT JOIN catalog_entries ce ON ce.id=(line->>'entry_id')::uuid
    WHERE e.created_at>=:start AND e.created_at<:end AND e.mode=:mode
      AND (:channel='all' OR e.channel=:channel)
), sales_rows AS (
    SELECT x.item_id, x.name, x.unit, x.channel, x.period_id,
      COALESCE(p.name, 'Без периода') AS period,
      SUM(CASE WHEN kind IN ('confirmed','pos') THEN quantity ELSE 0 END) AS paid_quantity,
      SUM(CASE WHEN kind IN ('completed','pos') THEN quantity ELSE 0 END) AS issued_quantity,
      SUM(CASE WHEN kind='cancelled' THEN quantity ELSE 0 END)
        AS cancelled_quantity,
      SUM(CASE WHEN kind='expired' THEN quantity ELSE 0 END) AS expired_quantity,
      SUM(CASE WHEN kind IN ('paid_cancelled','pos_return') THEN quantity ELSE 0 END)
        AS returned_quantity,
      SUM(CASE WHEN kind IN ('confirmed','pos') THEN quantity*price ELSE 0 END) AS paid_minor,
      SUM(CASE WHEN kind IN ('completed','pos') THEN quantity*price ELSE 0 END) AS issued_minor,
      SUM(CASE WHEN kind IN ('paid_cancelled','pos_return') THEN quantity*price ELSE 0 END)
        AS refund_minor
    FROM expanded x LEFT JOIN catalog_periods p ON p.id=x.period_id
    WHERE (CAST(:item AS uuid) IS NULL OR x.item_id=CAST(:item AS uuid))
      AND (CAST(:period AS uuid) IS NULL OR x.period_id=CAST(:period AS uuid))
    GROUP BY x.item_id, x.name, x.unit, x.channel, x.period_id, p.name
)
"""
SALES = SALES_BASE + ", aggregated AS (SELECT * FROM sales_rows)"
BY_ITEM = (
    SALES_BASE
    + """, by_item AS (
    SELECT item_id, name, unit, sum(paid_quantity - returned_quantity) AS quantity,
           sum(paid_minor - refund_minor) AS revenue_minor
    FROM sales_rows GROUP BY item_id, name, unit
), ranked AS (
    SELECT *, sum(revenue_minor) OVER () AS grand,
      sum(revenue_minor) OVER (ORDER BY revenue_minor DESC, name, item_id) AS running
    FROM by_item WHERE quantity > 0
)"""
)
TOP = (
    BY_ITEM
    + """, aggregated AS (
    SELECT item_id, name, unit, quantity, revenue_minor,
      to_char(round(100.0 * revenue_minor / NULLIF(grand, 0), 1), 'FM990.0') AS share
    FROM ranked
)"""
)
ABC = (
    BY_ITEM
    + """, aggregated AS (
    SELECT item_id, name, unit, revenue_minor,
      to_char(round(100.0 * revenue_minor / NULLIF(grand, 0), 1), 'FM990.0') AS share,
      to_char(round(100.0 * running / NULLIF(grand, 0), 1), 'FM990.0') AS cumulative,
      CASE WHEN 100.0 * (running - revenue_minor) / NULLIF(grand, 0) < 80 THEN 'A'
           WHEN 100.0 * (running - revenue_minor) / NULLIF(grand, 0) < 95 THEN 'B'
           ELSE 'C' END AS grade
    FROM ranked
)"""
)
UNSOLD = (
    SALES_BASE
    + """, sold AS (
    SELECT item_id, sum(paid_quantity) AS quantity FROM sales_rows GROUP BY item_id
), aggregated AS (
    SELECT i.id AS item_id, i.name, i.unit,
      COALESCE(NULLIF(i.category, ''), 'Без категории') AS category,
      COALESCE((SELECT sum(b.on_hand) FROM inventory_batches b
                WHERE b.item_id = i.id AND b.status = 'active'), 0) AS on_hand
    FROM inventory_items i LEFT JOIN sold ON sold.item_id = i.id
    WHERE i.kind IN ('prepared', 'purchased') AND COALESCE(sold.quantity, 0) = 0
      AND (CAST(:item AS uuid) IS NULL OR i.id = CAST(:item AS uuid))
)"""
)
RETURNS = (
    SALES_BASE
    + """, aggregated AS (
    SELECT item_id, name, unit,
      CASE WHEN channel = 'cashier' THEN 'Касса' ELSE 'Сайт' END AS channel,
      sum(returned_quantity) AS quantity, sum(refund_minor) AS amount_minor
    FROM sales_rows GROUP BY item_id, name, unit, channel HAVING sum(returned_quantity) > 0
)"""
)
PRODUCTION = """
WITH aggregated AS (
 SELECT i.id AS item_id, i.name, i.unit, count(*) AS batches, sum(p.actual_yield) AS quantity
 FROM production_batches p JOIN inventory_batches b ON b.id=p.id
 JOIN inventory_items i ON i.id=b.item_id
 WHERE p.created_at>=:start AND p.created_at<:end
 AND (CAST(:item AS uuid) IS NULL OR i.id=CAST(:item AS uuid))
 GROUP BY i.id, i.name, i.unit
)
"""
STOCK = """
WITH aggregated AS (
 SELECT i.id AS item_id, i.name, i.unit,
 COALESCE(sum(b.on_hand),0) AS on_hand, COALESCE(sum(b.reserved),0) AS reserved,
 COALESCE(sum(CASE WHEN b.status='active' AND b.expires_at>statement_timestamp()
   THEN b.on_hand-b.reserved ELSE 0 END),0) AS available,
 COALESCE(sum(CASE WHEN b.status!='active' OR b.expires_at<=statement_timestamp()
   THEN b.on_hand-b.reserved ELSE 0 END),0) AS blocked
 FROM inventory_items i LEFT JOIN inventory_batches b ON b.item_id=i.id
   AND b.received_at<=statement_timestamp()
 WHERE (CAST(:item AS uuid) IS NULL OR i.id=CAST(:item AS uuid))
 GROUP BY i.id, i.name, i.unit
)
"""
WRITEOFFS = """
WITH aggregated AS (
 SELECT i.id AS item_id, i.name, i.unit,
 SUM(CASE WHEN m.action='write_off' THEN -m.delta ELSE 0 END) AS written_off,
 SUM(CASE WHEN m.action='count' AND m.delta<0 THEN -m.delta ELSE 0 END) AS count_loss,
 SUM(CASE WHEN m.action='count' AND m.delta>0 THEN m.delta ELSE 0 END) AS count_gain
 FROM inventory_movements m JOIN inventory_batches b ON b.id=m.batch_id
 JOIN inventory_items i ON i.id=b.item_id
 WHERE m.created_at>=:start AND m.created_at<:end AND m.action IN ('write_off','count')
 AND (CAST(:item AS uuid) IS NULL OR i.id=CAST(:item AS uuid))
 GROUP BY i.id, i.name, i.unit
)
"""
INVENTORY = """
WITH aggregated AS (
 SELECT m.id AS item_id, i.name, i.unit, m.created_at,
   to_char(m.created_at AT TIME ZONE 'Asia/Almaty', 'DD.MM.YYYY HH24:MI') AS day_label,
   m."before" AS before_quantity, m."after" AS after_quantity, m.delta AS difference,
   m.reason, COALESCE(NULLIF(u.nickname, ''), u.name, 'Сотрудник') AS author
 FROM inventory_movements m JOIN inventory_batches b ON b.id=m.batch_id
 JOIN inventory_items i ON i.id=b.item_id LEFT JOIN identity_users u ON u.id=m.actor_id
 WHERE m.action='count' AND m.created_at>=:start AND m.created_at<:end
 AND (CAST(:item AS uuid) IS NULL OR i.id=CAST(:item AS uuid))
)
"""
EXPENSES = """
WITH aggregated AS (
 SELECT v.id AS item_id, v.supplier_name || ' · ' || v.number AS name, '' AS unit,
   v.received_at,
   to_char(v.received_at AT TIME ZONE 'Asia/Almaty', 'DD.MM.YYYY') AS day_label,
   v.goods_minor, v.expenses_minor, v.total_minor,
   v.paid_on_receipt_minor + COALESCE((SELECT sum(p.amount_minor)
     FROM inventory_invoice_payments p WHERE p.invoice_id=v.id), 0) AS paid_minor
 FROM inventory_invoices v WHERE v.received_at>=:start AND v.received_at<:end
)
"""
CASHBOOK = """
WITH flows AS (
 SELECT COALESCE(NULLIF(p.payment_method_name, ''), 'Касса') AS name,
   p.total_minor AS income, 0 AS outcome
 FROM pos_attempts p WHERE p.outcome='success' AND :mode='mock'
   AND p.created_at>=:start AND p.created_at<:end
 UNION ALL
 SELECT COALESCE(NULLIF(p.payment_method_name, ''), 'Касса'), 0, r.amount_minor
 FROM pos_returns r JOIN pos_attempts p ON p.id=r.sale_id
 WHERE :mode='mock' AND r.created_at>=:start AND r.created_at<:end
 UNION ALL
 SELECT 'Онлайн-оплата', CASE WHEN e.kind='confirmed' THEN d.total_minor ELSE 0 END,
   CASE WHEN e.kind='paid_cancelled' THEN d.total_minor ELSE 0 END
 FROM order_events e JOIN checkout_drafts d ON d.id=e.subject_id
 WHERE e.kind IN ('confirmed','paid_cancelled') AND :mode='mock'
   AND e.created_at>=:start AND e.created_at<:end
 UNION ALL
 SELECT v.payment_method_name, 0, v.paid_on_receipt_minor
 FROM inventory_invoices v WHERE v.received_at>=:start AND v.received_at<:end
 UNION ALL
 SELECT d.name, 0, p.amount_minor
 FROM inventory_invoice_payments p JOIN inventory_directories d ON d.id=p.payment_method_id
 WHERE p.paid_at>=:start AND p.paid_at<:end
), aggregated AS (
 SELECT md5(name)::uuid AS item_id, name, '' AS unit,
   sum(income) AS income_minor, sum(outcome) AS outcome_minor,
   sum(income) - sum(outcome) AS balance_minor
 FROM flows GROUP BY name
)
"""
DEBTS = """
WITH invoices AS (
 SELECT v.supplier_id, v.supplier_name, v.total_minor,
   v.paid_on_receipt_minor + COALESCE((SELECT sum(p.amount_minor)
     FROM inventory_invoice_payments p WHERE p.invoice_id=v.id), 0) AS paid_minor
 FROM inventory_invoices v
), aggregated AS (
 SELECT supplier_id AS item_id, supplier_name AS name, '' AS unit,
   count(*) AS invoices, sum(total_minor) AS total_minor, sum(paid_minor) AS paid_minor,
   sum(total_minor - paid_minor) AS debt_minor
 FROM invoices WHERE total_minor > paid_minor GROUP BY supplier_id, supplier_name
)
"""
HOURS = """
SELECT extract(hour FROM created_at AT TIME ZONE 'Asia/Almaty') AS hour,
  count(*) AS orders, sum(total) AS paid_minor
FROM (
  SELECT p.created_at, p.total_minor AS total FROM pos_attempts p
  WHERE p.outcome='success' AND p.mode=:mode
  UNION ALL
  SELECT e.created_at, d.total_minor FROM order_events e
  JOIN checkout_drafts d ON d.id=e.subject_id LEFT JOIN orders o ON o.id=d.id
  WHERE e.kind='confirmed' AND COALESCE(o.mode, 'mock')=:mode
) paid
WHERE created_at>=:start AND created_at<:end
GROUP BY 1 ORDER BY 1
"""
QUERIES: dict[ReportKind, str] = {
    "sales": SALES,
    "production": PRODUCTION,
    "stock": STOCK,
    "writeoffs": WRITEOFFS,
    "top": TOP,
    "abc": ABC,
    "unsold": UNSOLD,
    "returns": RETURNS,
    "inventory": INVENTORY,
    "expenses": EXPENSES,
    "cashbook": CASHBOOK,
    "debts": DEBTS,
}
ORDER: dict[ReportKind, str] = {
    "sales": "name, item_id, unit, channel, period_id",
    "top": "revenue_minor DESC, name, item_id",
    "abc": "revenue_minor DESC, name, item_id",
    "inventory": "created_at DESC, item_id",
    "expenses": "received_at DESC, item_id",
    "cashbook": "name, item_id",
    "debts": "debt_minor DESC, name, item_id",
}
NOTES: dict[ReportKind, str] = {
    "sales": (
        "Даты относятся к событиям оплаты, выдачи и отмены (Астана). "
        "Резерв не является продажей. Возвраты кассы и отмены оплаченных заказов — в «Возвраты»."
    ),
    "production": "Фактический выпуск за выбранные даты. Единицы разных товаров не суммируются.",
    "stock": "Остаток на момент запроса, не исторический. Даты не применяются.",
    "writeoffs": (
        "Списания и расхождения пересчёта за выбранные даты. Расход при "
        "производстве и продаже сюда не входит."
    ),
    "top": "Товары по выручке за вычетом возвратов, от большей к меньшей.",
    "abc": "A — товары, дающие первые 80% выручки, B — следующие 15%, C — остальные 5%.",
    "unsold": "Готовые и покупные товары без оплаченных продаж за выбранные даты.",
    "returns": "Возвраты на кассе и отмены оплаченных заказов сайта.",
    "inventory": "Каждый пересчёт партии: учётное и фактическое количество, причина и автор.",
    "expenses": "Накладные прихода за выбранные даты: товары, дополнительные расходы и оплата.",
    "cashbook": (
        "Движение денег по способам оплаты: продажи и возвраты, оплаты поставщикам. "
        "Оплата сайта и кассы тестовая."
    ),
    "debts": "Текущие долги поставщикам по всем непогашенным накладным; даты не применяются.",
}


class PostgresReportRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def read(self, kind: ReportKind, filters: ReportFilter, offset: int, limit: int) -> Report:
        start, end = filters.bounds()
        columns = COLUMNS[kind]
        if kind == "sales" and filters.mode == "real":
            columns = tuple(
                replace(c, label=c.label.replace("ДЕМО", "(реальные)")) for c in columns
            )
        # Keys are fixed code constants, never user-supplied SQL identifiers.
        pairs = ", ".join(f"'{c.key}', {c.key}::text" for c in columns)
        money = [c.key for c in columns if c.format == "money"]
        totals = ", ".join(f"'{key}', COALESCE(sum({key}),0)::text" for key in money)
        totals_sql = (
            f"(SELECT jsonb_build_object({totals}) FROM aggregated)" if money else "'{}'::jsonb"
        )
        quantities = [c.key for c in columns if c.format == "quantity"]
        unit_pairs = ", ".join(f"'{key}', COALESCE(sum({key}),0)::text" for key in quantities)
        unit_sql = f"""COALESCE((SELECT jsonb_object_agg(unit, summary) FROM
          (SELECT unit, jsonb_build_object({unit_pairs}) AS summary
           FROM aggregated GROUP BY unit) units),'{{}}'::jsonb)"""
        order = ORDER.get(kind, "name, item_id, unit")
        query = (
            QUERIES[kind]
            + f"""
        SELECT statement_timestamp() AS generated_at,
          COALESCE((SELECT jsonb_agg(row) FROM (
            SELECT jsonb_build_object({pairs}) AS row FROM aggregated
            ORDER BY {order} OFFSET :offset LIMIT :limit
          ) page),'[]'::jsonb) AS rows,
          {totals_sql} AS totals, {unit_sql} AS unit_totals,
          (SELECT count(*) FROM aggregated) AS total_rows
        """
        )
        row = (
            self.connection.execute(
                text(query),
                {
                    "start": start,
                    "end": end,
                    "item": filters.item_id,
                    "period": filters.period_id,
                    "channel": filters.channel,
                    "mode": filters.mode,
                    "offset": offset,
                    "limit": limit,
                },
            )
            .mappings()
            .one()
        )
        note = NOTES[kind]
        return Report(
            kind,
            row["generated_at"],
            columns,
            row["rows"],
            row["totals"],
            row["unit_totals"],
            row["total_rows"],
            offset,
            limit,
            note,
        )

    def dashboard(self, filters: ReportFilter) -> Dashboard:
        start, end = filters.bounds()
        query = (
            SALES
            + """,
        products AS (
            SELECT i.id, i.name, COALESCE(sum(a.paid_quantity),0) AS quantity
            FROM inventory_items i LEFT JOIN aggregated a ON a.item_id=i.id
            WHERE i.kind IN ('prepared','purchased')
            GROUP BY i.id, i.name
        )
        SELECT statement_timestamp() AS generated_at,
          (SELECT jsonb_build_object('paid_minor', COALESCE(sum(paid_minor),0)::text,
             'issued_minor', COALESCE(sum(issued_minor),0)::text,
             'refund_minor', COALESCE(sum(refund_minor),0)::text,
             'products', (SELECT count(*)::text FROM products WHERE quantity>0))
           FROM aggregated) AS totals,
          COALESCE((SELECT jsonb_agg(row) FROM (
            SELECT jsonb_build_object('id', id::text, 'name', name,
                'quantity', quantity::text) AS row
            FROM products WHERE quantity>0 ORDER BY quantity DESC, name, id LIMIT 5
          ) leaders), '[]'::jsonb) AS top,
          COALESCE((SELECT jsonb_agg(row) FROM (
            SELECT jsonb_build_object('id', id::text, 'name', name,
                'quantity', quantity::text) AS row
            FROM products ORDER BY quantity, name, id LIMIT 5
          ) slow), '[]'::jsonb) AS low
        """
        )
        row = (
            self.connection.execute(
                text(query),
                {
                    "start": start,
                    "end": end,
                    "mode": filters.mode,
                    "channel": filters.channel,
                    "item": None,
                    "period": None,
                },
            )
            .mappings()
            .one()
        )
        hours = self.connection.execute(
            text(HOURS), {"start": start, "end": end, "mode": filters.mode}
        ).mappings()
        totals = dict(row["totals"])
        orders = 0
        hourly: list[dict[str, str]] = []
        for hour in hours:
            orders += int(hour["orders"])
            hourly.append(
                {
                    "hour": str(int(hour["hour"])),
                    "paid_minor": str(hour["paid_minor"]),
                    "orders": str(hour["orders"]),
                }
            )
        paid = int(totals.get("paid_minor", "0"))
        totals["orders"] = str(orders)
        totals["average_minor"] = str(paid // orders if orders else 0)
        return Dashboard(row["generated_at"], totals, row["top"], row["low"], hourly)

    def options(self, target: str, offset: int, limit: int) -> list[dict[str, str]]:
        table = "inventory_items" if target == "items" else "catalog_periods"
        label = (
            "name"
            if target == "items"
            else (
                "name || ' · ' || to_char(starts_at AT TIME ZONE 'Asia/Almaty', "
                "'DD.MM.YYYY HH24:MI')"
            )
        )
        return [
            dict(r)
            for r in self.connection.execute(
                text(
                    f"SELECT id::text AS id, {label} AS name FROM {table} "
                    "ORDER BY name, id OFFSET :offset LIMIT :limit"
                ),
                {"offset": offset, "limit": limit},
            ).mappings()
        ]


class PostgresReportUnitOfWork:
    def __init__(self, engine: Engine, authorize: Callable[[Connection, str], None]) -> None:
        self.engine, self.authorizer = engine, authorize

    def __enter__(self) -> "PostgresReportUnitOfWork":
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.connection.execute(text("SET TRANSACTION READ ONLY"))
        self.repository: ReportRepository = PostgresReportRepository(self.connection)
        return self

    def authorize(self, token: str) -> None:
        self.connection.execute(text("SELECT pg_advisory_xact_lock_shared(71001)"))
        self.authorizer(self.connection, token)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            self.transaction.rollback()
        finally:
            self.connection.close()
