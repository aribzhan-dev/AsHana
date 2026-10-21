import type { components } from "./schema";
import { ApiError, record, request } from "./http";
import { inventoryRu as t } from "../locales/inventory";
export type StockItem = components["schemas"]["ItemResponse"];
export type StockBatch = components["schemas"]["BatchResponse"];
export type StockMovement = components["schemas"]["MovementResponse"];
export type Receipt = components["schemas"]["ReceiptInput"];
export type StockChange = components["schemas"]["ChangeInput"];
export type ItemInput = components["schemas"]["ItemInput"];
function invalid(): never {
  throw new ApiError(0, t.genericError);
}
function list<T>(value: unknown, parse: (value: unknown) => T): T[] {
  if (!Array.isArray(value)) return invalid();
  return value.map(parse);
}
export function item(value: unknown): StockItem {
  if (
    !record(value) ||
    typeof value.id !== "string" ||
    typeof value.name !== "string" ||
    typeof value.kind !== "string" ||
    !Object.hasOwn(t.kinds, value.kind) ||
    typeof value.unit !== "string" ||
    !["kg", "l", "pcs", "portion"].includes(value.unit)
  )
    return invalid();
  return value as StockItem;
}
export function batch(value: unknown): StockBatch {
  if (
    !record(value) ||
    typeof value.item_kind !== "string" ||
    !Object.hasOwn(t.kinds, value.item_kind)
  )
    return invalid();
  for (const field of [
    "id",
    "item_id",
    "item_name",
    "label",
    "source",
    "actor_id",
  ])
    if (typeof value[field] !== "string") return invalid();
  for (const field of ["on_hand", "reserved", "free", "available"])
    if (typeof value[field] !== "string" || !/^\d+(\.\d+)?$/.test(value[field]))
      return invalid();
  for (const field of ["received_at", "expires_at", "created_at"])
    if (
      typeof value[field] !== "string" ||
      !Number.isFinite(Date.parse(value[field]))
    )
      return invalid();
  if (
    typeof value.status !== "string" ||
    !Object.hasOwn(t.states, value.status) ||
    typeof value.unit !== "string" ||
    !Object.hasOwn(t.units, value.unit) ||
    typeof value.version !== "number" ||
    !Number.isSafeInteger(value.version) ||
    typeof value.total_cost_minor !== "number" ||
    !Number.isSafeInteger(value.total_cost_minor)
  )
    return invalid();
  return value as StockBatch;
}
function movement(value: unknown): StockMovement {
  if (!record(value)) return invalid();
  for (const field of [
    "id",
    "batch_id",
    "reason",
    "actor_id",
    "status_before",
    "status_after",
  ])
    if (typeof value[field] !== "string") return invalid();
  for (const field of ["delta", "before", "after"])
    if (
      typeof value[field] !== "string" ||
      !/^-?\d+(\.\d+)?$/.test(value[field])
    )
      return invalid();
  if (
    typeof value.action !== "string" ||
    !Object.hasOwn(t.actions, value.action) ||
    typeof value.created_at !== "string" ||
    !Number.isFinite(Date.parse(value.created_at)) ||
    typeof value.version !== "number" ||
    !Number.isSafeInteger(value.version)
  )
    return invalid();
  return value as StockMovement;
}
export function operation(
  value: unknown,
): components["schemas"]["OperationResponse"] {
  if (
    !record(value) ||
    typeof value.subject_id !== "string" ||
    typeof value.version !== "number" ||
    !Number.isSafeInteger(value.version)
  )
    return invalid();
  return { subject_id: value.subject_id, version: value.version };
}
const write = (path: string, body: unknown, key: string) =>
  request(`/inventory${path}`, "POST", body, { "Idempotency-Key": key }).then(
    operation,
  );
export const inventoryApi = {
  items: (offset = 0) =>
    request(`/inventory/items?offset=${offset}&limit=100`).then((value) =>
      list(value, item),
    ),
  batches: (offset = 0, warehouse = "", query = "") =>
    request(
      `/inventory/batches?offset=${offset}&limit=20${warehouse ? `&warehouse_id=${warehouse}` : ""}&query=${encodeURIComponent(query)}`,
    ).then((value) => list(value, batch)),
  movements: (id: string, offset = 0) =>
    request(
      `/inventory/batches/${id}/movements?offset=${offset}&limit=20`,
    ).then((value) => list(value, movement)),
  createItem: (data: ItemInput, key: string) => write("/items", data, key),
  receive: (data: Receipt, key: string) => write("/receipts", data, key),
  change: (id: string, data: StockChange, key: string) =>
    write(`/batches/${id}/changes`, data, key),
};
