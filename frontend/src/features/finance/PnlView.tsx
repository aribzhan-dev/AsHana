import type { FinanceDetails, Pnl } from "../../shared/api/finance";
import { percent } from "../../shared/api/finance";
import { shortMoney } from "../../shared/lib/inventory-validation";

function Row({
  label,
  value,
  strong = false,
  minus = false,
  hint,
}: {
  label: string;
  value: number;
  strong?: boolean;
  minus?: boolean;
  hint?: string;
}) {
  return (
    <tr className={strong ? "pnl-total" : ""}>
      <td>
        {minus ? "− " : ""}
        {label}
        {hint && <small className="muted"> {hint}</small>}
      </td>
      <td className={`num ${value < 0 ? "debt" : ""}`}>{shortMoney(value)}</td>
    </tr>
  );
}

/** Profit and loss for a month, with both profit methods side by side. */
export function PnlView({ pnl }: { pnl: Pnl }) {
  return (
    <div className="form-stack">
      <div className="kpi-grid">
        <div className="kpi">
          <span>Выручка</span>
          <strong>{shortMoney(pnl.net_revenue)}</strong>
        </div>
        <div className="kpi">
          <span>Валовая прибыль</span>
          <strong>{shortMoney(pnl.gross_profit)}</strong>
        </div>
        <div className="kpi">
          <span>Упрощённая прибыль</span>
          <strong className={pnl.simple_profit < 0 ? "debt" : ""}>
            {shortMoney(pnl.simple_profit)}
          </strong>
        </div>
        <div className="kpi">
          <span>Чистая прибыль</span>
          <strong className={pnl.net_profit < 0 ? "debt" : ""}>
            {shortMoney(pnl.net_profit)}
          </strong>
        </div>
      </div>
      <div className="table-wrap">
        <table className="report-table pnl-table">
          <tbody>
            <Row label="Продажи" value={pnl.revenue} />
            <Row label="Возвраты" value={pnl.returns} minus />
            <Row label="Выручка" value={pnl.net_revenue} strong />
            <Row
              label="Себестоимость проданного"
              value={pnl.cost_of_goods}
              minus
              hint="по закупочным ценам партий и расходу сырья"
            />
            <Row label="Валовая прибыль" value={pnl.gross_profit} strong />
            <Row label="Списания и недостача" value={pnl.writeoffs} minus />
            <Row
              label="Доп. расходы по накладным"
              value={pnl.invoice_expenses}
              minus
            />
            {Object.entries(pnl.expenses).map(([name, value]) => (
              <Row key={name} label={name} value={value} minus />
            ))}
            <Row label="Упрощённая прибыль" value={pnl.simple_profit} strong />
            <Row label="Комиссия банка" value={pnl.commission} minus />
            <Row
              label="Зарплата"
              value={pnl.payroll}
              minus
              hint="оклад, дни, часы и проценты от продаж"
            />
            <Row label="Полная прибыль" value={pnl.full_profit} strong />
            <Row label="Проценты от прибыли" value={pnl.profit_shares} minus />
            <Row label="Чистая прибыль" value={pnl.net_profit} strong />
          </tbody>
        </table>
      </div>
      <p className="field-hint">
        Упрощённая прибыль — до зарплаты и комиссии банка. Полная — после них.
        Процент от прибыли сотрудникам и дивиденды считаются от выбранной из
        двух.
      </p>
    </div>
  );
}

export function CommissionView({ pnl }: { pnl: Pnl }) {
  const rows = pnl.sales_by_method as {
    id: string;
    name: string;
    commission_bp: number;
    amount: number;
  }[];
  return (
    <div className="table-wrap">
      <table className="report-table">
        <thead>
          <tr>
            <th>Способ оплаты</th>
            <th className="num">Оборот</th>
            <th className="num">Комиссия, %</th>
            <th className="num">Комиссия</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.name}</td>
              <td className="num">{shortMoney(r.amount)}</td>
              <td className="num">{percent(r.commission_bp)}</td>
              <td className="num">
                {shortMoney(Math.round((r.amount * r.commission_bp) / 10000))}
              </td>
            </tr>
          ))}
          <tr className="pnl-total">
            <td>Итого</td>
            <td className="num">
              {shortMoney(rows.reduce((n, r) => n + r.amount, 0))}
            </td>
            <td />
            <td className="num">{shortMoney(pnl.commission)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function PlanView({
  pnl,
  details,
  month,
}: {
  pnl: Pnl;
  details: FinanceDetails;
  month: string;
}) {
  const [year, m] = month.split("-").map(Number) as [number, number];
  const days = new Date(year, m, 0).getDate();
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Almaty",
  }).format(new Date());
  const passed = today.startsWith(month)
    ? Number(today.slice(8, 10))
    : today > month
      ? days
      : 0;
  const rows = [
    {
      category: "Вся столовая",
      fact: pnl.net_revenue,
      plan: details.plans.find((p) => !p.category),
    },
    ...details.plans
      .filter((p) => p.category)
      .map((p) => ({
        category: p.category,
        fact: details.categories[p.category] ?? 0,
        plan: p,
      })),
  ];
  return (
    <div className="table-wrap">
      <table className="report-table">
        <thead>
          <tr>
            <th>План</th>
            <th className="num">Цель</th>
            <th className="num">Факт</th>
            <th className="num">Выполнено</th>
            <th className="num">Прогноз на месяц</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const target = r.plan?.target_minor ?? 0;
            const done = target ? Math.round((r.fact / target) * 1000) / 10 : 0;
            const forecast = passed ? Math.round((r.fact / passed) * days) : 0;
            return (
              <tr key={r.category}>
                <td>{r.category}</td>
                <td className="num">{target ? shortMoney(target) : "—"}</td>
                <td className="num">{shortMoney(r.fact)}</td>
                <td className="num">
                  {target ? (
                    <span className="share">
                      <i style={{ width: `${Math.min(100, done)}%` }} />
                      {done.toLocaleString("ru-RU")}%
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="num">{forecast ? shortMoney(forecast) : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
