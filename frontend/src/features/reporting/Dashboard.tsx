import { useEffect, useState } from "react";
import type { Staff } from "../../shared/api/identity";
import { ApiError } from "../../shared/api/http";
import {
  reportsApi,
  reportValue,
  type DashboardData,
} from "../../shared/api/reporting";
import { almatyNow } from "../../shared/lib/inventory-validation";
import { errorMessage } from "../../shared/lib/forms";
import { Alert, Card, LoadingState } from "../../shared/ui/Feedback";
import { Input } from "../../shared/ui/Input";
import { Button } from "../../shared/ui/Button";
function Ranking({
  title,
  items,
}: {
  title: string;
  items: Record<string, string>[];
}) {
  const max = items.reduce(
    (n, i) => (BigInt(i.quantity!) > n ? BigInt(i.quantity!) : n),
    1n,
  );
  return (
    <Card>
      <h2>{title}</h2>
      {items.length ? (
        <ol className="ranking">
          {items.map((item, index) => (
            <li key={item.id}>
              <span className="ranking-number">{index + 1}</span>
              <div>
                <div className="ranking-label">
                  <strong>{item.name}</strong>
                  <span>{item.quantity} шт./порц.</span>
                </div>
                <div className="chart-track" aria-hidden="true">
                  <span
                    style={{
                      width: `${Number((BigInt(item.quantity!) * 100n) / max)}%`,
                    }}
                  />
                </div>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">Продаж за этот период пока нет.</p>
      )}
    </Card>
  );
}
export function Dashboard({
  user,
  onExpired,
}: {
  user: Staff;
  onExpired: () => void;
}) {
  const today = almatyNow().slice(0, 10);
  const [start, setStart] = useState(today),
    [end, setEnd] = useState(today);
  const [range, setRange] = useState({ start: today, end: today });
  const [data, setData] = useState<DashboardData | null>(null),
    [busy, setBusy] = useState(true),
    [error, setError] = useState("");
  const allowed = user.permissions.includes("reporting.read");
  useEffect(() => {
    if (!allowed) return;
    let alive = true;
    void reportsApi
      .dashboard(range.start, range.end)
      .then((result) => {
        if (alive) setData(result);
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
  }, [range, allowed, onExpired]);
  return (
    <>
      <div className="dashboard-heading">
        <div>
          <p className="eyebrow">Рабочий день</p>
          <h1>Обзор столовой</h1>
          <p className="muted">
            Здравствуйте, {user.name}. Все основные показатели — здесь.
          </p>
        </div>
        <a
          className="button button-primary"
          href={
            user.permissions.includes("pos.sell")
              ? "/staff/pos"
              : "/staff/profile"
          }
        >
          {user.permissions.includes("pos.sell")
            ? "Открыть кассу"
            : "Мой профиль"}
        </a>
      </div>
      {allowed ? (
        <>
          <form
            className="dashboard-range"
            onSubmit={(e) => {
              e.preventDefault();
              if (
                !start ||
                !end ||
                end < start ||
                (Date.parse(end) - Date.parse(start)) / 86400000 > 365
              ) {
                setError("Выберите период от 1 до 366 дней.");
                return;
              }
              setData(null);
              setBusy(true);
              setError("");
              setRange({ start, end });
            }}
          >
            <Input
              label="С даты"
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
            <Input
              label="По дату"
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
            <Button type="submit" loading={busy}>
              Применить
            </Button>
          </form>
          {error && <Alert>{error}</Alert>}
          {busy ? (
            <LoadingState />
          ) : (
            data && (
              <>
                <div className="metrics-grid">
                  {[
                    [
                      "Оплачено",
                      reportValue(data.totals.paid_minor || "0", "money"),
                    ],
                    [
                      "Выдано на сумму",
                      reportValue(data.totals.issued_minor || "0", "money"),
                    ],
                    [
                      "Возвраты",
                      reportValue(data.totals.refund_minor || "0", "money"),
                    ],
                    ["Продано позиций", data.totals.products || "0"],
                  ].map(([label, value]) => (
                    <Card key={label}>
                      <span className="muted">{label}</span>
                      <strong className="metric-value">{value}</strong>
                    </Card>
                  ))}
                </div>
                <div className="dashboard-charts">
                  <Ranking title="Лидеры продаж" items={data.top} />
                  <Ranking title="Продаются реже" items={data.low} />
                </div>
                <a href="/staff/reports">Открыть подробные отчёты →</a>
              </>
            )
          )}
        </>
      ) : (
        <Card>
          <h2>Всё готово к работе</h2>
          <p>
            Выберите нужный раздел в меню. Доступные действия определяются вашей
            ролью.
          </p>
        </Card>
      )}
    </>
  );
}
