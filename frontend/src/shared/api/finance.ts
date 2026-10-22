import type { components } from "./schema";
import { ApiError, record, request } from "./http";
import { operation } from "./inventory";

export type FinanceMonth = components["schemas"]["MonthResponse"];
export type Pnl = components["schemas"]["PnlResponse"];
export type Accrual = components["schemas"]["AccrualResponse"];
export type Worker = components["schemas"]["WorkerResponse"];
export type FinanceDetails = components["schemas"]["DetailsResponse"];
export type WorkerInput = components["schemas"]["WorkerInput"];
export type MyShift = components["schemas"]["MyShiftResponse"];

function invalid(): never {
  throw new ApiError(0, "Не удалось прочитать финансовые данные");
}
const integer = (v: unknown) =>
  typeof v === "number" && Number.isSafeInteger(v);

function month(v: unknown): FinanceMonth {
  if (!record(v) || !record(v.pnl) || !Array.isArray(v.payroll))
    return invalid();
  const pnl = v.pnl as Record<string, unknown>;
  for (const key of [
    "revenue",
    "net_revenue",
    "cost_of_goods",
    "gross_profit",
    "simple_profit",
    "full_profit",
    "net_profit",
    "payroll",
    "commission",
  ])
    if (!integer(pnl[key])) return invalid();
  for (const a of v.payroll)
    if (
      !record(a) ||
      !record(a.worker) ||
      !integer(a.total) ||
      !integer(a.balance)
    )
      return invalid();
  return v as FinanceMonth;
}

function details(v: unknown): FinanceDetails {
  if (
    !record(v) ||
    ![
      v.expenses,
      v.payments,
      v.dividends,
      v.shifts,
      v.owners,
      v.plans,
      v.staff,
    ].every(Array.isArray) ||
    !record(v.categories) ||
    !record(v.daily)
  )
    return invalid();
  return v as FinanceDetails;
}

const keyed = (path: string, method: string, body: unknown, key: string) =>
  request(path, method, body, { "Idempotency-Key": key }).then(operation);

export const financeApi = {
  month: (m: string) => request(`/finance/month?month=${m}`).then(month),
  details: (m: string) => request(`/finance/details?month=${m}`).then(details),
  commission: (methodId: string, bp: number, key: string) =>
    keyed(
      `/finance/payment-methods/${encodeURIComponent(methodId)}/commission`,
      "PUT",
      { commission_bp: bp },
      key,
    ),
  expense: (body: components["schemas"]["ExpenseInput"], key: string) =>
    keyed("/finance/expenses", "POST", body, key),
  plan: (body: components["schemas"]["PlanInput"], key: string) =>
    keyed("/finance/plans", "PUT", body, key),
  owner: (
    id: string | null,
    body: components["schemas"]["OwnerInput"],
    key: string,
  ) =>
    keyed(
      id ? `/finance/owners/${encodeURIComponent(id)}` : "/finance/owners",
      id ? "PUT" : "POST",
      body,
      key,
    ),
  dividend: (
    ownerId: string,
    body: components["schemas"]["PayoutInput"],
    key: string,
  ) =>
    keyed(
      `/finance/owners/${encodeURIComponent(ownerId)}/dividends`,
      "POST",
      body,
      key,
    ),
  worker: (id: string | null, body: WorkerInput, key: string) =>
    keyed(
      id ? `/finance/workers/${encodeURIComponent(id)}` : "/finance/workers",
      id ? "PUT" : "POST",
      body,
      key,
    ),
  pay: (
    workerId: string,
    body: components["schemas"]["SalaryInput"],
    key: string,
  ) =>
    keyed(
      `/finance/workers/${encodeURIComponent(workerId)}/payments`,
      "POST",
      body,
      key,
    ),
  shift: (
    workerId: string,
    body: components["schemas"]["ShiftInput"],
    key: string,
  ) =>
    keyed(
      `/finance/workers/${encodeURIComponent(workerId)}/shifts`,
      "POST",
      body,
      key,
    ),
  voidShift: (shiftId: string, note: string, key: string) =>
    keyed(
      `/finance/shifts/${encodeURIComponent(shiftId)}/void`,
      "POST",
      { note },
      key,
    ),
  myShift: () =>
    request("/finance/my-shift").then((v) => {
      if (!record(v) || typeof v.linked !== "boolean") return invalid();
      return v as MyShift;
    }),
  toggleShift: (start: boolean, key: string) =>
    keyed("/finance/my-shift", "POST", { start }, key),
};

export function percent(bp: number) {
  return `${(bp / 100).toLocaleString("ru-RU", { maximumFractionDigits: 2 })}%`;
}

export function basisPoints(text: string): number | undefined {
  const value = Number(text.replace(",", ".").trim() || "0");
  if (!Number.isFinite(value) || value < 0 || value > 100) return undefined;
  return Math.round(value * 100);
}

export function currentMonth() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Almaty",
    year: "numeric",
    month: "2-digit",
  }).format(new Date());
}
