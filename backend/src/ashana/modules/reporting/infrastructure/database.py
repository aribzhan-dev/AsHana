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
SALES = """
WITH events AS (
    SELECT d.lines, e.kind, e.created_at, COALESCE(o.mode, 'mock') AS mode,
           'online' AS channel, s.period_id
    FROM order_events e JOIN checkout_drafts d ON d.id=e.subject_id
    JOIN order_slots s ON s.id=d.slot_id LEFT JOIN orders o ON o.id=d.id
    WHERE e.kind IN ('confirmed','completed','paid_cancelled','cancelled','expired')
    UNION ALL
    SELECT p.lines, 'pos', p.created_at, p.mode, 'cashier', NULL::uuid
    FROM pos_attempts p WHERE p.outcome='success'
), expanded AS (
    SELECT (line->>'item_id')::uuid AS item_id, line->>'name' AS name,
           line->>'unit' AS unit, (line->>'quantity')::bigint AS quantity,
           (line->>'price_minor')::bigint AS price, e.kind, e.channel,
           COALESCE(e.period_id, ce.period_id) AS period_id
    FROM events e CROSS JOIN LATERAL jsonb_array_elements(e.lines) line
    LEFT JOIN catalog_entries ce ON ce.id=(line->>'entry_id')::uuid
    WHERE e.created_at>=:start AND e.created_at<:end AND e.mode=:mode
      AND (:channel='all' OR e.channel=:channel)
), aggregated AS (
    SELECT x.item_id, x.name, x.unit, x.channel, x.period_id,
      COALESCE(p.name, 'Без периода') AS period,
      SUM(CASE WHEN kind IN ('confirmed','pos') THEN quantity ELSE 0 END) AS paid_quantity,
      SUM(CASE WHEN kind IN ('completed','pos') THEN quantity ELSE 0 END) AS issued_quantity,
      SUM(CASE WHEN kind='cancelled' THEN quantity ELSE 0 END)
        AS cancelled_quantity,
      SUM(CASE WHEN kind='expired' THEN quantity ELSE 0 END) AS expired_quantity,
      SUM(CASE WHEN kind IN ('confirmed','pos') THEN quantity*price ELSE 0 END) AS paid_minor,
      SUM(CASE WHEN kind IN ('completed','pos') THEN quantity*price ELSE 0 END) AS issued_minor,
      SUM(CASE WHEN kind='paid_cancelled' THEN quantity*price ELSE 0 END) AS refund_minor
    FROM expanded x LEFT JOIN catalog_periods p ON p.id=x.period_id
    WHERE (CAST(:item AS uuid) IS NULL OR x.item_id=CAST(:item AS uuid))
      AND (CAST(:period AS uuid) IS NULL OR x.period_id=CAST(:period AS uuid))
    GROUP BY x.item_id, x.name, x.unit, x.channel, x.period_id, p.name
)
"""
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
QUERIES: dict[ReportKind, str] = {
    "sales": SALES,
    "production": PRODUCTION,
    "stock": STOCK,
    "writeoffs": WRITEOFFS,
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
        order = "name, item_id, unit" + (", channel, period_id" if kind == "sales" else "")
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
        note = {
            "sales": (
                "Даты относятся к событиям оплаты, выдачи и отмены (Астана). "
                "Резерв не является продажей. Неявка пока не учитывается."
            ),
            "production": (
                "Фактический выпуск за выбранные даты. Единицы разных товаров не суммируются."
            ),
            "stock": (
                "Остаток на момент запроса, не исторический. Даты не применяются. "
                "Резервы показаны по учёту; истёкшие освобождает фоновый обработчик."
            ),
            "writeoffs": (
                "Списания и расхождения пересчёта за выбранные даты. Расход при "
                "производстве и продаже сюда не входит."
            ),
        }[kind]
        if kind == "sales":
            note += (
                ""
                if filters.mode == "mock"
                else " Реальная оплата не подключена; реальных поступлений нет."
            )
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
        return Dashboard(row["generated_at"], row["totals"], row["top"], row["low"])

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
