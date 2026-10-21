import type { components } from "./schema";
import { ApiError, record, request } from "./http";
import { publicEntry } from "./catalog";
export type PosInput = components["schemas"]["PosInput"];
export type Sale = components["schemas"]["PosResponse"];
export function sale(value: unknown): Sale {
  if (
    !record(value) ||
    typeof value.id !== "string" ||
    typeof value.actor_id !== "string" ||
    value.mode !== "mock" ||
    value.currency !== "KZT" ||
    !["success", "failed", "timeout"].includes(String(value.outcome)) ||
    typeof value.created_at !== "string" ||
    !Number.isFinite(Date.parse(value.created_at)) ||
    typeof value.total_minor !== "number" ||
    !Number.isSafeInteger(value.total_minor) ||
    value.total_minor < 0 ||
    !Array.isArray(value.lines) ||
    !value.lines.length ||
    value.lines.some(
      (l: unknown) =>
        !record(l) ||
        typeof l.entry_id !== "string" ||
        typeof l.name !== "string" ||
        typeof l.portion_label !== "string" ||
        !["pcs", "portion"].includes(String(l.unit)) ||
        typeof l.quantity !== "number" ||
        !Number.isSafeInteger(l.quantity) ||
        l.quantity < 1 ||
        typeof l.price_minor !== "number" ||
        !Number.isSafeInteger(l.price_minor) ||
        l.price_minor < 0,
    )
  )
    throw new ApiError(0, "Не удалось прочитать данные кассы");
  return value as Sale;
}
function list<T>(v: unknown, parse: (v: unknown) => T): T[] {
  if (!Array.isArray(v))
    throw new ApiError(0, "Не удалось прочитать данные кассы");
  return v.map(parse);
}
export const posApi = {
  menu: (offset = 0) =>
    request(`/pos/menu?offset=${offset}&limit=20`).then((v) =>
      list(v, publicEntry),
    ),
  history: (offset = 0) =>
    request(`/pos/sales?offset=${offset}&limit=20`).then((v) => list(v, sale)),
  sell: (body: PosInput, key: string) =>
    request("/pos/sales", "POST", body, { "Idempotency-Key": key }).then(sale),
};
