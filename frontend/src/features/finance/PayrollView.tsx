import { useState } from "react";
import {
  percent,
  type Accrual,
  type FinanceDetails,
  type Worker,
} from "../../shared/api/finance";
import type { Directory } from "../../shared/api/receiving";
import { shortMoney } from "../../shared/lib/inventory-validation";
import { Button } from "../../shared/ui/Button";
import { MoneyList } from "./MoneyList";
import { WorkerDialog } from "./WorkerDialog";
import { PayDialog } from "./PayDialog";
import { kinds } from "./payment-kinds";

function scheme(w: Worker): string {
  const parts = [];
  if (w.monthly_minor) parts.push(`оклад ${shortMoney(w.monthly_minor)}`);
  if (w.daily_minor) parts.push(`${shortMoney(w.daily_minor)} в день`);
  if (w.hourly_minor) parts.push(`${shortMoney(w.hourly_minor)} в час`);
  if (w.sales_bp)
    parts.push(
      `${percent(w.sales_bp)} от ${w.sales_base === "personal" ? "своих продаж" : "продаж столовой"}`,
    );
  if (w.profit_bp)
    parts.push(
      `${percent(w.profit_bp)} от ${w.profit_base === "simple" ? "упрощённой" : "полной"} прибыли`,
    );
  return parts.join(" + ") || "схема не задана";
}

export function PayrollView({
  month,
  payroll,
  details,
  methods,
  onChanged,
}: {
  month: string;
  payroll: Accrual[];
  details: FinanceDetails;
  methods: Directory[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<Worker | "new" | null>(null),
    [paying, setPaying] = useState<Accrual | null>(null);
  const total = payroll.reduce((n, a) => n + a.total, 0),
    paid = payroll.reduce((n, a) => n + a.paid, 0);
  return (
    <div className="form-stack">
      <div className="kpi-grid">
        <div className="kpi">
          <span>Начислено за месяц</span>
          <strong>{shortMoney(total)}</strong>
        </div>
        <div className="kpi">
          <span>Выплачено</span>
          <strong>{shortMoney(paid)}</strong>
        </div>
        <div className="kpi">
          <span>Осталось выплатить</span>
          <strong className={total - paid > 0 ? "debt" : ""}>
            {shortMoney(total - paid)}
          </strong>
        </div>
      </div>
      <div className="button-row">
        <Button icon="plus" onClick={() => setEditing("new")}>
          Добавить сотрудника
        </Button>
      </div>
      <div className="table-wrap">
        <table className="report-table payroll-table">
          <thead>
            <tr>
              <th>Сотрудник</th>
              <th className="num">Дней / часов</th>
              <th className="num">Оклад, дни, часы</th>
              <th className="num">% от продаж</th>
              <th className="num">% от прибыли</th>
              <th className="num">Начислено</th>
              <th className="num">Выплачено</th>
              <th className="num">Долг</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {payroll.map((a) => (
              <tr key={a.worker.id} className={a.worker.active ? "" : "muted"}>
                <td>
                  {a.worker.name}
                  <small className="muted">
                    {[a.worker.position, scheme(a.worker)]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </td>
                <td className="num">
                  {a.days} / {a.hours.replace(".", ",")}
                </td>
                <td className="num">
                  {shortMoney(a.monthly + a.daily + a.hourly)}
                </td>
                <td className="num">{shortMoney(a.sales)}</td>
                <td className="num">{shortMoney(a.profit)}</td>
                <td className="num">
                  <strong>{shortMoney(a.total)}</strong>
                </td>
                <td className="num">{shortMoney(a.paid)}</td>
                <td className={`num ${a.balance > 0 ? "debt" : ""}`}>
                  {shortMoney(a.balance)}
                </td>
                <td className="row-actions">
                  <Button variant="secondary" onClick={() => setPaying(a)}>
                    Выплатить
                  </Button>
                  <Button variant="ghost" onClick={() => setEditing(a.worker)}>
                    Изменить
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!payroll.length && (
        <p className="muted">
          Добавьте сотрудников: оклад, оплата за день или час, процент от продаж
          или прибыли — в любом сочетании.
        </p>
      )}
      <h3>Выплаты за месяц</h3>
      <MoneyList
        rows={details.payments.map((p) => ({
          ...p,
          label: `${p.subject_name} · ${kinds[p.kind as keyof typeof kinds] ?? p.kind}`,
        }))}
      />
      {editing && (
        <WorkerDialog
          worker={editing === "new" ? null : editing}
          staff={details.staff}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
      {paying && (
        <PayDialog
          accrual={paying}
          month={month}
          methods={methods}
          onClose={() => setPaying(null)}
          onSaved={() => {
            setPaying(null);
            onChanged();
          }}
        />
      )}
    </div>
  );
}
