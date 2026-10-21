import type { components } from "./schema";
import { ApiError, record, request } from "./http";
import { item, operation } from "./inventory";
import { catalogRu as t } from "../locales/catalog";
export type Period = components["schemas"]["PeriodResponse"];
export type PeriodInput = components["schemas"]["PeriodInput"];
export type MenuEntry = components["schemas"]["MenuEntryResponse"];
export type MenuEntryInput = components["schemas"]["MenuEntryInput"];
export type PublicMenu = components["schemas"]["PublicMenuResponse"];
export type PublicEntry = components["schemas"]["PublicMenuEntry"];
function invalid(): never {
  throw new ApiError(0, t.invalidData);
}
function list<T>(value: unknown, parse: (value: unknown) => T): T[] {
  if (!Array.isArray(value)) return invalid();
  return value.map(parse);
}
function texts(value: Record<string, unknown>, keys: string[]) {
  if (keys.some((key) => typeof value[key] !== "string")) invalid();
}
function instant(value: unknown) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value)))
    invalid();
}
function integer(value: unknown, min: number, max = Number.MAX_SAFE_INTEGER) {
  if (
    typeof value !== "number" ||
    !Number.isSafeInteger(value) ||
    value < min ||
    value > max
  )
    invalid();
}
function published(value: unknown) {
  if (typeof value !== "boolean") invalid();
}
function period(value: unknown): Period {
  if (!record(value)) return invalid();
  texts(value, ["id", "name", "actor_id"]);
  for (const key of ["starts_at", "ends_at", "created_at", "updated_at"])
    instant(value[key]);
  integer(value.version, 1);
  published(value.published);
  return value as Period;
}
function product(value: unknown): Record<string, unknown> {
  if (!record(value)) return invalid();
  texts(value, [
    "id",
    "period_id",
    "name",
    "description",
    "portion_label",
    "category",
  ]);
  if (value.unit !== "pcs" && value.unit !== "portion") invalid();
  integer(value.price_minor, 0, 999999999999);
  return value;
}
function entry(value: unknown): MenuEntry {
  const v = product(value);
  texts(v, ["actor_id", "item_id"]);
  integer(v.version, 1);
  published(v.published);
  instant(v.created_at);
  instant(v.updated_at);
  return v as MenuEntry;
}
export function publicEntry(value: unknown): PublicEntry {
  const v = product(value);
  texts(v, ["period_name"]);
  instant(v.starts_at);
  instant(v.ends_at);
  integer(v.available, 1);
  return v as PublicEntry;
}
function menu(value: unknown): PublicMenu {
  if (!record(value) || value.currency !== "KZT") return invalid();
  instant(value.generated_at);
  return {
    generated_at: value.generated_at as string,
    currency: "KZT",
    entries: list(value.entries, publicEntry),
  };
}
const write = (path: string, body: unknown, key: string, method = "POST") =>
  request(`/catalog${path}`, method, body, { "Idempotency-Key": key }).then(
    operation,
  );
export const catalogApi = {
  menu: (offset = 0) =>
    request(`/catalog/menu?upcoming=true&offset=${offset}&limit=20`).then(menu),
  periods: (day: string, offset = 0) =>
    request(
      `/catalog/periods?day=${encodeURIComponent(day)}&offset=${offset}&limit=20`,
    ).then((v) => list(v, period)),
  entries: (id: string, offset = 0) =>
    request(
      `/catalog/periods/${encodeURIComponent(id)}/entries?offset=${offset}&limit=20`,
    ).then((v) => list(v, entry)),
  items: (kind: "prepared" | "purchased", offset = 0) =>
    request(`/catalog/items?kind=${kind}&offset=${offset}&limit=100`).then(
      (v) => list(v, item),
    ),
  savePeriod: (id: string | undefined, body: PeriodInput, key: string) =>
    write(`/periods${id ? `/${id}` : ""}`, body, key, id ? "PUT" : "POST"),
  saveEntry: (
    periodId: string,
    id: string | undefined,
    body: MenuEntryInput,
    key: string,
  ) =>
    write(
      `/periods/${periodId}/entries${id ? `/${id}` : ""}`,
      body,
      key,
      id ? "PUT" : "POST",
    ),
};
