import { DetailsButton } from "../../shared/ui/DetailsButton";
import { useEffect, useState } from "react";
import {
  reportsApi,
  reportValue,
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
import { Alert, Card, LoadingState } from "../../shared/ui/Feedback";
function today() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Almaty",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
export function ReportBoard({ onExpired }: { onExpired: () => void }) {
  const initial: Filters = {
    start: today(),
    end: today(),
    item_id: "",
    period_id: "",
    channel: "all",
    mode: "mock",
  };
  const [kind, setKind] = useState<Kind>("sales"),
    [filters, setFilters] = useState(initial);
  const [active, setActive] = useState<{
    kind: Kind;
    filters: Filters;
    offset: number;
  }>({ kind: "sales", filters: initial, offset: 0 });
  const [data, setData] = useState<Report | null>(null),
    [busy, setBusy] = useState(true),
    [error, setError] = useState("");
  const [items, setItems] = useState<Option[]>([]),
    [periods, setPeriods] = useState<Option[]>([]);
  const [optionError, setOptionError] = useState(""),
    [optionAttempt, setOptionAttempt] = useState(0),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    async function load(target: "items" | "periods") {
      const rows: Option[] = [];
      for (let offset = 0; ; offset += 100) {
        const page = await reportsApi.options(target, offset);
        rows.push(...page);
        if (page.length < 100) break;
      }
      return rows;
    }
    void Promise.all([load("items"), load("periods")])
      .then(([i, p]) => {
        if (alive) {
          setItems(i);
          setPeriods(p);
          setOptionError("");
        }
      })
      .catch((e) => {
        if (alive) setOptionError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, [optionAttempt]);
  useEffect(() => {
    let alive = true;
    void reportsApi
      .read(active.kind, active.filters, active.offset)
      .then((result) => {
        if (alive) {
          setData(result);
          setError("");
        }
      })
      .catch((e) => {
        if (alive) {
          if (e instanceof ApiError && e.status === 401) onExpired();
          else setError(errorMessage(e));
        }
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
    };
  }, [active, attempt, onExpired]);
  function field(key: keyof Filters, value: string) {
    setFilters({ ...filters, [key]: value });
  }
  function apply() {
    if (kind === "stock") {
      setBusy(true);
      setData(null);
      setActive({
        kind,
        filters: { ...filters, start: today(), end: today() },
        offset: 0,
      });
      return;
    }
    const a = Date.parse(filters.start),
      b = Date.parse(filters.end);
    if (
      !Number.isFinite(a) ||
      !Number.isFinite(b) ||
      b < a ||
      b - a > 365 * 86400000
    ) {
      setError(t.dateError);
      return;
    }
    setBusy(true);
    setData(null);
    setActive({ kind, filters: { ...filters }, offset: 0 });
  }
  function page(offset: number) {
    setBusy(true);
    setData(null);
    setActive({ ...active, offset });
  }
  return (
    <div className="form-stack">
      <Card className="form-stack">
        <h2>{t.filters}</h2>
        <p className="field-hint">{t.scope}</p>
        <form
          className="form-stack"
          onSubmit={(e) => {
            e.preventDefault();
            apply();
          }}
        >
          <Select
            label="Вид отчёта"
            value={kind}
            onChange={(e) => setKind(e.target.value as Kind)}
          >
            {Object.entries(t.kinds).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </Select>
          <div className="report-filters">
            <Input
              label={t.start}
              type="date"
              value={filters.start}
              disabled={kind === "stock"}
              onChange={(e) => field("start", e.target.value)}
            />
            <Input
              label={t.end}
              type="date"
              value={filters.end}
              disabled={kind === "stock"}
              onChange={(e) => field("end", e.target.value)}
            />
            <Select
              label={t.item}
              value={filters.item_id}
              onChange={(e) => field("item_id", e.target.value)}
            >
              <option value="">Все товары</option>
              {items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </Select>
            {kind === "sales" && (
              <>
                <Select
                  label={t.period}
                  value={filters.period_id}
                  onChange={(e) => field("period_id", e.target.value)}
                >
                  <option value="">Все периоды</option>
                  {periods.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </Select>
                <Select
                  label={t.channel}
                  value={filters.channel}
                  onChange={(e) => field("channel", e.target.value)}
                >
                  <option value="all">Все каналы</option>
                  <option value="online">Онлайн</option>
                  <option value="cashier">Касса</option>
                </Select>
                <Select
                  label={t.mode}
                  value={filters.mode}
                  onChange={(e) => field("mode", e.target.value)}
                >
                  <option value="mock">Текущие операции</option>
                  <option value="real">Реальные деньги (не подключено)</option>
                </Select>
              </>
            )}
          </div>
          <Button type="submit" loading={busy}>
            {t.apply}
          </Button>
        </form>
        {optionError && (
          <>
            <Alert>{optionError}</Alert>
            <Button
              variant="secondary"
              onClick={() => setOptionAttempt((n) => n + 1)}
            >
              Обновить справочники
            </Button>
          </>
        )}
      </Card>
      {error && (
        <>
          <Alert>{error}</Alert>
          <Button
            variant="secondary"
            onClick={() => {
              setBusy(true);
              setAttempt((n) => n + 1);
            }}
          >
            Повторить загрузку
          </Button>
        </>
      )}
      {busy ? (
        <LoadingState />
      ) : (
        data && (
          <section className="form-stack" aria-label="Результат отчёта">
            <h2>{t.kinds[data.kind]}</h2>
            <p>{data.note}</p>
            {data.kind !== "stock" && (
              <p>
                Даты отчёта (Астана): {active.filters.start} —{" "}
                {active.filters.end}
              </p>
            )}
            <p>
              {t.actual}: {stockDate(data.generated_at)}
            </p>
            <Card className="form-stack">
              <h3>{t.totals}</h3>
              <div className="report-summary">
                {Object.entries(data.totals).map(([key, value]) => (
                  <div key={key}>
                    <p className="muted">
                      {data.columns.find((c) => c.key === key)?.label}
                    </p>
                    <strong>{reportValue(value, "money")}</strong>
                  </div>
                ))}
              </div>
              {Object.entries(data.unit_totals).map(([unit, values]) => (
                <div key={unit}>
                  <h4>{reportValue(unit, "text")}</h4>
                  <dl className="report-summary">
                    {Object.entries(values).map(([key, value]) => (
                      <div key={key}>
                        <dt>
                          {data.columns.find((c) => c.key === key)?.label}
                        </dt>
                        <dd>{reportValue(value, "quantity")}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
              <p>Найдено строк: {data.total_rows}</p>
            </Card>
            {!data.rows.length ? (
              <p>{t.empty}</p>
            ) : (
              <div className="compact-list">
                {data.rows.map((row, index) => (
                  <Card
                    key={`${active.offset}-${index}`}
                    className="compact-record"
                  >
                    <h3>{row.name}</h3>
                    <p className="muted">
                      {data.columns
                        .filter((c) => c.key !== "name")
                        .slice(-2)
                        .map(
                          (c) =>
                            `${c.label}: ${reportValue(row[c.key]!, c.format)}`,
                        )
                        .join(" · ")}
                    </p>
                    <DetailsButton title={String(row.name)}>
                      <dl className="detail-list">
                        {data.columns
                          .filter((c) => c.key !== "name")
                          .map((c) => (
                            <div key={c.key}>
                              <dt>{c.label}</dt>
                              <dd>{reportValue(row[c.key]!, c.format)}</dd>
                            </div>
                          ))}
                      </dl>
                    </DetailsButton>
                  </Card>
                ))}
              </div>
            )}
            <div className="stock-pagination">
              <Button
                variant="secondary"
                disabled={active.offset === 0}
                onClick={() => page(Math.max(0, active.offset - 20))}
              >
                Назад
              </Button>
              <span>
                {data.total_rows ? active.offset + 1 : 0}–
                {Math.min(active.offset + data.rows.length, data.total_rows)} из{" "}
                {data.total_rows}
              </span>
              <Button
                variant="secondary"
                disabled={active.offset + 20 >= data.total_rows}
                onClick={() => page(active.offset + 20)}
              >
                Далее
              </Button>
            </div>
          </section>
        )
      )}
    </div>
  );
}
