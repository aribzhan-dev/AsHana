import { useCallback, useEffect, useState } from "react";
import {
  currentMonth,
  financeApi,
  type FinanceDetails,
  type FinanceMonth,
} from "../../shared/api/finance";
import { ApiError } from "../../shared/api/http";
import { receivingApi, type Directory } from "../../shared/api/receiving";
import { errorMessage } from "../../shared/lib/forms";
import { Input } from "../../shared/ui/Input";
import { ErrorState, LoadingState } from "../../shared/ui/Feedback";
import { CommissionView, PlanView, PnlView } from "./PnlView";
import { PayrollView } from "./PayrollView";
import { TimesheetView } from "./TimesheetView";
import {
  CommissionEditor,
  ExpensesView,
  OwnersView,
  PlanEditor,
} from "./MoneyViews";

const tabs = {
  pnl: "Итоги месяца",
  payroll: "Зарплата",
  timesheet: "Табель",
  expenses: "Расходы",
  owners: "Учредители",
  plan: "План продаж",
  commission: "Комиссии",
} as const;
type Tab = keyof typeof tabs;

export function FinanceBoard({ onExpired }: { onExpired: () => void }) {
  const [tab, setTab] = useState<Tab>(() => {
    const hash = window.location.hash.slice(1);
    return hash in tabs ? (hash as Tab) : "pnl";
  });
  const [month, setMonth] = useState(currentMonth()),
    [data, setData] = useState<FinanceMonth | null>(null),
    [details, setDetails] = useState<FinanceDetails | null>(null),
    [methods, setMethods] = useState<Directory[]>([]),
    [categories, setCategories] = useState<Directory[]>([]),
    [itemCategories, setItemCategories] = useState<string[]>([]),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  useEffect(() => {
    let alive = true;
    const first = `${month}-01`;
    Promise.all([
      financeApi.month(first),
      financeApi.details(first),
      receivingApi.directories("payment_method"),
      receivingApi.directories("expense_category"),
      receivingApi.directories("category"),
    ])
      .then(([m, d, pm, ec, cat]) => {
        if (!alive) return;
        setData(m);
        setDetails(d);
        setMethods(pm);
        setCategories(ec);
        setItemCategories(cat.map((c) => c.name));
        setError("");
      })
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) onExpired();
        else setError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, [month, attempt, onExpired]);

  return (
    <div className="form-stack">
      <div className="report-head">
        <div className="chips" role="tablist" aria-label="Разделы финансов">
          {(Object.keys(tabs) as Tab[]).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              className="chip"
              aria-selected={tab === key}
              aria-pressed={tab === key}
              onClick={() => {
                window.history.replaceState(null, "", `#${key}`);
                setTab(key);
              }}
            >
              {tabs[key]}
            </button>
          ))}
        </div>
        <Input
          label="Месяц"
          type="month"
          value={month}
          onChange={(e) => {
            if (!e.target.value) return;
            setData(null);
            setMonth(e.target.value);
          }}
        />
      </div>
      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data || !details ? (
        <LoadingState />
      ) : tab === "pnl" ? (
        <PnlView pnl={data.pnl} />
      ) : tab === "payroll" ? (
        <PayrollView
          month={month}
          payroll={data.payroll}
          details={details}
          methods={methods}
          onChanged={reload}
        />
      ) : tab === "timesheet" ? (
        <TimesheetView
          payroll={data.payroll}
          details={details}
          onChanged={reload}
        />
      ) : tab === "expenses" ? (
        <ExpensesView
          details={details}
          categories={categories}
          methods={methods}
          onChanged={reload}
        />
      ) : tab === "owners" ? (
        <OwnersView
          month={month}
          pnl={data.pnl}
          details={details}
          methods={methods}
          onChanged={reload}
        />
      ) : tab === "plan" ? (
        <div className="form-stack">
          <PlanView pnl={data.pnl} details={details} month={month} />
          <PlanEditor
            month={month}
            details={details}
            categories={itemCategories}
            onChanged={reload}
          />
        </div>
      ) : (
        <div className="form-stack">
          <CommissionView pnl={data.pnl} />
          <CommissionEditor methods={methods} onChanged={reload} />
        </div>
      )}
    </div>
  );
}
