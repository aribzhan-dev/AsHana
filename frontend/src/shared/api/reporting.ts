import type { components } from "./schema";
import { ApiError, record, request } from "./http";
export type Report = components["schemas"]["ReportResponse"];
export type Kind = Report["kind"];
export type Option = components["schemas"]["ReportOption"];
export type Filters = {
  start: string;
  end: string;
  item_id: string;
  period_id: string;
  channel: string;
  mode: string;
};
const numeric = /^-?[0-9]+(?:\.[0-9]+)?$/;
function invalid(): never {
  throw new ApiError(0, "Не удалось прочитать отчёт");
}
function strings(v: unknown): v is Record<string, string> {
  return record(v) && Object.values(v).every((x) => typeof x === "string");
}
export function parseReport(v: unknown): Report {
  if (
    !record(v) ||
    ![
      "sales",
      "production",
      "stock",
      "writeoffs",
      "top",
      "abc",
      "unsold",
      "returns",
      "inventory",
      "expenses",
      "cashbook",
      "debts",
    ].includes(String(v.kind)) ||
    typeof v.generated_at !== "string" ||
    !Number.isFinite(Date.parse(v.generated_at)) ||
    typeof v.note !== "string" ||
    !Array.isArray(v.columns) ||
    !v.columns.length ||
    !Array.isArray(v.rows) ||
    !strings(v.totals) ||
    !record(v.unit_totals)
  )
    return invalid();
  for (const c of v.columns)
    if (
      !record(c) ||
      typeof c.key !== "string" ||
      typeof c.label !== "string" ||
      !["text", "quantity", "money"].includes(String(c.format))
    )
      invalid();
  const columns = v.columns as Report["columns"];
  for (const row of v.rows)
    if (
      !strings(row) ||
      columns.some(
        (c) =>
          typeof row[c.key] !== "string" ||
          (c.format !== "text" &&
            !(c.format === "money" ? /^-?[0-9]+$/ : numeric).test(row[c.key]!)),
      )
    )
      invalid();
  if (
    Object.values(v.totals).some((x) => !/^-?[0-9]+$/.test(x)) ||
    Object.values(v.unit_totals).some(
      (x) => !strings(x) || Object.values(x).some((n) => !numeric.test(n)),
    )
  )
    invalid();
  for (const key of ["offset", "limit", "total_rows"])
    if (
      typeof v[key] !== "number" ||
      !Number.isSafeInteger(v[key]) ||
      v[key] < 0
    )
      invalid();
  return v as Report;
}
export type DashboardData = {
  generated_at: string;
  totals: Record<string, string>;
  top: Record<string, string>[];
  low: Record<string, string>[];
  hours: Record<string, string>[];
};
export const reportsApi = {
  dashboard: (start: string, end: string): Promise<DashboardData> =>
    request(`/reports/dashboard?${new URLSearchParams({ start, end })}`).then(
      (v) => {
        if (
          !record(v) ||
          typeof v.generated_at !== "string" ||
          !Number.isFinite(Date.parse(v.generated_at)) ||
          !strings(v.totals) ||
          Object.values(v.totals).some((n) => !/^[0-9]+$/.test(n))
        )
          return invalid();
        if (
          !Array.isArray(v.hours) ||
          v.hours.some(
            (h) =>
              !strings(h) ||
              !/^[0-9]+$/.test(h.hour || "") ||
              !/^[0-9]+$/.test(h.paid_minor || ""),
          )
        )
          return invalid();
        for (const key of ["top", "low"])
          if (
            !Array.isArray(v[key]) ||
            v[key].some(
              (r) =>
                !strings(r) ||
                !r.id ||
                !r.name ||
                !/^[0-9]+$/.test(r.quantity || ""),
            )
          )
            return invalid();
        return v as DashboardData;
      },
    ),
  read: (kind: Kind, filters: Filters, offset = 0) => {
    const query = new URLSearchParams({
      start: filters.start,
      end: filters.end,
      offset: String(offset),
      limit: "20",
    });
    if (filters.item_id) query.set("item_id", filters.item_id);
    if (filters.period_id) query.set("period_id", filters.period_id);
    query.set("channel", filters.channel);
    query.set("mode", filters.mode);
    return request(`/reports/${kind}?${query}`).then(parseReport);
  },
  options: (target: "items" | "periods", offset = 0): Promise<Option[]> =>
    request(`/reports/options/${target}?offset=${offset}&limit=100`).then(
      (v) => {
        if (
          !Array.isArray(v) ||
          v.some(
            (x) =>
              !record(x) ||
              typeof x.id !== "string" ||
              typeof x.name !== "string",
          )
        )
          return invalid();
        return v as Option[];
      },
    ),
};
export function reportValue(value: string, format: string) {
  if (format === "money") {
    const n = BigInt(value),
      abs = n < 0n ? -n : n;
    return `${n < 0n ? "−" : ""}${(abs / 100n).toLocaleString("ru-RU")},${String(abs % 100n).padStart(2, "0")} ₸`;
  }
  if (format === "quantity")
    return value.includes(".")
      ? value.replace(/0+$/, "").replace(/\.$/, "").replace(".", ",")
      : value;
  return (
    (
      {
        online: "Онлайн",
        cashier: "Касса",
        kg: "кг",
        l: "л",
        pcs: "шт",
        portion: "порц.",
      } as Record<string, string>
    )[value] || value
  );
}
