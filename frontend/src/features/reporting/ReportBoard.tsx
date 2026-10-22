import { useEffect, useState } from "react";
import {
  reportsApi,
  reportValue,
  type DashboardData,
  type Report,
  type Kind,
  type Filters,
  type Option,
} from "../../shared/api/reporting";
import { ApiError } from "../../shared/api/http";
import { errorMessage } from "../../shared/lib/forms";
import { stockDate } from "../../shared/lib/inventory-validation";
import { reportingRu as t } from "../../shared/locales/reporting";
import { Input, Select } from "../../shared/ui/Input";
import { Button } from "../../shared/ui/Button";
import { Alert, EmptyState, LoadingState } from "../../shared/ui/Feedback";
import { Icon, type IconName } from "../../shared/ui/Icon";

type View = Kind | "dashboard";
const groups: { title: string; items: [View, IconName][] }[] = [
  {
    title: "Продажи",
    items: [
      ["dashboard", "chart"],
      ["sales", "receipt"],
      ["top", "heart"],
      ["abc", "grid"],
      ["unsold", "minus"],
      ["returns", "arrow-left"],
    ],
  },
  {
    title: "Склад",
    items: [
      ["stock", "box"],
      ["inventory", "check"],
      ["writeoffs", "close"],
      ["production", "utensils"],
    ],
  },
  {
    title: "Деньги",
    items: [
      ["expenses", "bag"],
      ["cashbook", "receipt"],
      ["debts", "alert"],
    ],
  },
];
// Reports that describe the current moment ignore the date range.
const undated: View[] = ["stock", "debts"];
const viewName = (view: View) =>
  view === "dashboard" ? "Сводка по продажам" : t.kinds[view];

function day(offset = 0) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Almaty",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(Date.now() - offset * 86_400_000));
}
const presets: [string, number][] = [
  ["Сегодня", 0],
  ["7 дней", 6],
  ["30 дней", 29],
];

function initialView(): View {
  const hash = window.location.hash.slice(1);
  return groups.some((g) => g.items.some(([v]) => v === hash))
    ? (hash as View)
    : "dashboard";
}

// Month-based money reports live on the finance page; the report menu links there.
const financeLinks: [string, string, IconName][] = [
  ["Финансовый результат", "pnl", "chart"],
  ["Зарплата", "payroll", "user"],
  ["Отработанное время", "timesheet", "clock"],
  ["План продаж", "plan", "check"],
  ["Комиссия банка", "commission", "receipt"],
  ["Дивиденды", "owners", "heart"],
];

export function ReportBoard({
  onExpired,
  finance = false,
}: {
  onExpired: () => void;
  finance?: boolean;
}) {
  const [view, setView] = useState<View>(initialView);
  const [filters, setFilters] = useState<Filters>({
    start: day(6),
    end: day(),
    item_id: "",
    period_id: "",
    channel: "all",
    mode: "mock",
  });
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Report | null>(null),
    [dashboard, setDashboard] = useState<DashboardData | null>(null),
    [busy, setBusy] = useState(true),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  const [items, setItems] = useState<Option[]>([]);

  useEffect(() => {
    let alive = true;
    void reportsApi
      .options("items")
      .then((list) => {
        if (alive) setItems(list);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const valid =
    Date.parse(filters.end) >= Date.parse(filters.start) &&
    Date.parse(filters.end) - Date.parse(filters.start) <= 365 * 86_400_000;

  useEffect(() => {
    if (!valid) return;
    let alive = true;
    const request =
      view === "dashboard"
        ? reportsApi.dashboard(filters.start, filters.end).then((d) => {
            if (alive) setDashboard(d);
          })
        : reportsApi
            .read(
              view,
              undated.includes(view)
                ? { ...filters, start: day(), end: day() }
                : filters,
              offset,
            )
            .then((r) => {
              if (alive) setData(r);
            });
    request
      .then(() => {
        if (alive) setError("");
      })
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) onExpired();
        else setError(errorMessage(e));
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
    };
  }, [view, filters, offset, attempt, valid, onExpired]);

  function choose(next: View) {
    window.history.replaceState(null, "", `#${next}`);
    setBusy(true);
    setData(null);
    setDashboard(null);
    setOffset(0);
    setView(next);
  }
  function change(next: Partial<Filters>) {
    setBusy(true);
    setOffset(0);
    setFilters({ ...filters, ...next });
  }

  return (
    <div className="report-layout">
      <nav className="report-nav" aria-label="Виды отчётов">
        {groups.map((group) => (
          <div key={group.title}>
            <p className="report-nav-title">{group.title}</p>
            {group.items.map(([key, icon]) => (
              <button
                key={key}
                type="button"
                aria-current={view === key ? "page" : undefined}
                onClick={() => choose(key)}
              >
                <Icon name={icon} />
                <span>{viewName(key)}</span>
              </button>
            ))}
          </div>
        ))}
        {finance && (
          <div>
            <p className="report-nav-title">Финансы</p>
            {financeLinks.map(([label, tab, icon]) => (
              <a
                key={tab}
                className="report-link"
                href={`/staff/finance#${tab}`}
              >
                <Icon name={icon} />
                <span>{label}</span>
              </a>
            ))}
          </div>
        )}
      </nav>

      <section className="report-main" aria-label={viewName(view)}>
        <header className="report-head">
          <h2>{viewName(view)}</h2>
          {!undated.includes(view) && (
            <div className="report-presets" role="group" aria-label="Период">
              {presets.map(([label, back]) => (
                <button
                  key={label}
                  type="button"
                  className="chip"
                  aria-pressed={
                    filters.start === day(back) && filters.end === day()
                  }
                  onClick={() => change({ start: day(back), end: day() })}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </header>

        {!undated.includes(view) && (
          <div className="report-filters">
            <Input
              label={t.start}
              type="date"
              value={filters.start}
              onChange={(e) => change({ start: e.target.value })}
            />
            <Input
              label={t.end}
              type="date"
              value={filters.end}
              onChange={(e) => change({ end: e.target.value })}
            />
            {[
              "sales",
              "top",
              "abc",
              "unsold",
              "returns",
              "inventory",
              "writeoffs",
              "production",
            ].includes(view) && (
              <Select
                label={t.item}
                value={filters.item_id}
                onChange={(e) => change({ item_id: e.target.value })}
              >
                <option value="">Все товары</option>
                {items.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </Select>
            )}
            {["sales", "top", "abc", "returns"].includes(view) && (
              <Select
                label={t.channel}
                value={filters.channel}
                onChange={(e) => change({ channel: e.target.value })}
              >
                <option value="all">Сайт и касса</option>
                <option value="online">Сайт</option>
                <option value="cashier">Касса</option>
              </Select>
            )}
          </div>
        )}
        {!valid && <Alert>{t.dateError}</Alert>}
        {error && (
          <Alert>
            {error}{" "}
            <Button
              variant="secondary"
              onClick={() => {
                setBusy(true);
                setAttempt((n) => n + 1);
              }}
            >
              Повторить
            </Button>
          </Alert>
        )}
        {busy ? (
          <LoadingState />
        ) : view === "dashboard" ? (
          dashboard && <SalesDashboard data={dashboard} />
        ) : (
          data && (
            <ReportResult
              data={data}
              offset={offset}
              onPage={(next) => {
                setBusy(true);
                setOffset(next);
              }}
            />
          )
        )}
      </section>
    </div>
  );
}

function SalesDashboard({ data }: { data: DashboardData }) {
  const hours = Array.from({ length: 24 }, (_, hour) => {
    const found = data.hours.find((h) => Number(h.hour) === hour);
    return { hour, paid: Number(found?.paid_minor ?? 0) };
  });
  const active = hours.filter((h, i) => h.paid || (i >= 7 && i <= 21));
  const max = Math.max(1, ...active.map((h) => h.paid));
  const best = Math.max(1, ...data.top.map((r) => Number(r.quantity)));
  const cards: [string, string, string][] = [
    ["Выручка", reportValue(data.totals.paid_minor ?? "0", "money"), "money"],
    ["Заказов и чеков", data.totals.orders ?? "0", "text"],
    [
      "Средний чек",
      reportValue(data.totals.average_minor ?? "0", "money"),
      "money",
    ],
    [
      "Возвраты",
      reportValue(data.totals.refund_minor ?? "0", "money"),
      "money",
    ],
  ];
  return (
    <div className="form-stack">
      <div className="kpi-grid">
        {cards.map(([label, value]) => (
          <div className="kpi" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="report-panels">
        <div className="report-panel">
          <h3>Продажи по часам</h3>
          <div className="hour-chart" role="img" aria-label="Выручка по часам">
            {active.map((h) => (
              <div key={h.hour} className="hour-bar">
                <span
                  style={{ height: `${Math.round((h.paid / max) * 100)}%` }}
                  title={`${h.hour}:00 — ${reportValue(String(h.paid), "money")}`}
                />
                <small>{h.hour}</small>
              </div>
            ))}
          </div>
        </div>
        <div className="report-panel">
          <h3>Популярные позиции</h3>
          {!data.top.length ? (
            <p className="muted">Продаж за этот период нет.</p>
          ) : (
            <ol className="rank-list">
              {data.top.map((row) => (
                <li key={row.id}>
                  <span>{row.name}</span>
                  <strong>{row.quantity}</strong>
                  <i
                    style={{
                      width: `${Math.round((Number(row.quantity) / best) * 100)}%`,
                    }}
                  />
                </li>
              ))}
            </ol>
          )}
          <h3>Продаются реже</h3>
          <ol className="rank-list muted-list">
            {data.low.map((row) => (
              <li key={row.id}>
                <span>{row.name}</span>
                <strong>{row.quantity}</strong>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <p className="field-hint">Актуально на {stockDate(data.generated_at)}</p>
    </div>
  );
}

function ReportResult({
  data,
  offset,
  onPage,
}: {
  data: Report;
  offset: number;
  onPage: (offset: number) => void;
}) {
  const money = Object.entries(data.totals);
  const shareKey = data.columns.find((c) => c.key === "share")?.key;
  return (
    <div className="form-stack">
      {money.length > 0 && (
        <div className="kpi-grid">
          {money.map(([key, value]) => (
            <div className="kpi" key={key}>
              <span>{data.columns.find((c) => c.key === key)?.label}</span>
              <strong>{reportValue(value, "money")}</strong>
            </div>
          ))}
        </div>
      )}
      <p className="muted report-note">{data.note}</p>
      {!data.rows.length ? (
        <EmptyState title={t.empty} />
      ) : (
        <div className="table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                {data.columns.map((c) => (
                  <th key={c.key} className={c.format !== "text" ? "num" : ""}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, index) => (
                <tr key={`${offset}-${index}`}>
                  {data.columns.map((c) => (
                    <td
                      key={c.key}
                      className={
                        c.format !== "text" || c.key === shareKey ? "num" : ""
                      }
                    >
                      {c.key === "grade" ? (
                        <span className={`grade grade-${row[c.key]}`}>
                          {row[c.key]}
                        </span>
                      ) : c.key === shareKey ? (
                        <span className="share">
                          <i style={{ width: `${row[c.key]}%` }} />
                          {row[c.key]}%
                        </span>
                      ) : (
                        reportValue(row[c.key]!, c.format)
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.total_rows > 20 && (
        <div className="stock-pagination">
          <Button
            variant="secondary"
            disabled={offset === 0}
            onClick={() => onPage(Math.max(0, offset - 20))}
          >
            Назад
          </Button>
          <span>
            {offset + 1}–{Math.min(offset + data.rows.length, data.total_rows)}{" "}
            из {data.total_rows}
          </span>
          <Button
            variant="secondary"
            disabled={offset + 20 >= data.total_rows}
            onClick={() => onPage(offset + 20)}
          >
            Далее
          </Button>
        </div>
      )}
      <p className="field-hint">
        {t.actual}: {stockDate(data.generated_at)}
      </p>
    </div>
  );
}
