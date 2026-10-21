import type { components } from "./schema";
import { ApiError, record, request } from "./http";
export type Order = components["schemas"]["OrderResponse"];
export type Slot = components["schemas"]["SlotResponse"];
export type SlotInput = components["schemas"]["SlotInput"];
export type CheckoutInput = components["schemas"]["CheckoutInput"];
export type KitchenTransition = components["schemas"]["KitchenTransition"];
export type OrderConfig = components["schemas"]["OrderConfiguration"];
function invalid(): never {
  throw new ApiError(0, "Не удалось получить данные заказов");
}
const isInteger = (v: unknown) =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const isTime = (v: unknown) =>
  typeof v === "string" && Number.isFinite(Date.parse(v));
function list<T>(v: unknown, parse: (v: unknown) => T): T[] {
  if (!Array.isArray(v)) return invalid();
  return v.map(parse);
}
function order(v: unknown): Order {
  if (
    !record(v) ||
    typeof v.id !== "string" ||
    !isInteger(v.total_minor) ||
    !isInteger(v.version) ||
    v.currency !== "KZT" ||
    typeof v.stock_issue !== "boolean" ||
    (v.pickup_code !== null &&
      v.pickup_code !== undefined &&
      (typeof v.pickup_code !== "string" ||
        !/^[0-9A-F]{8}$/.test(v.pickup_code))) ||
    ![
      "pending_payment",
      "confirmed",
      "preparing",
      "ready",
      "completed",
      "cancelled",
      "expired",
      "no_show",
    ].includes(String(v.status)) ||
    ![
      v.created_at,
      v.updated_at,
      v.expires_at,
      v.slot_starts_at,
      v.slot_ends_at,
    ].every(isTime) ||
    !Array.isArray(v.lines) ||
    !v.lines.every(
      (l) =>
        record(l) &&
        typeof l.name === "string" &&
        typeof l.portion_label === "string" &&
        typeof l.entry_id === "string" &&
        ["pcs", "portion"].includes(String(l.unit)) &&
        isInteger(l.quantity) &&
        Number(l.quantity) > 0 &&
        isInteger(l.price_minor),
    )
  )
    return invalid();
  return v as Order;
}
function slot(v: unknown): Slot {
  if (
    !record(v) ||
    typeof v.id !== "string" ||
    typeof v.period_id !== "string" ||
    ![v.starts_at, v.ends_at, v.cutoff_at].every(isTime) ||
    !isInteger(v.capacity) ||
    !isInteger(v.occupied) ||
    !isInteger(v.version) ||
    typeof v.enabled !== "boolean"
  )
    return invalid();
  return v as Slot;
}
let guestPromise: Promise<unknown> | undefined;
function guest() {
  guestPromise ??= request("/orders/guest", "POST").catch((e) => {
    guestPromise = undefined;
    throw e;
  });
  return guestPromise;
}
const keyed = (path: string, body: unknown, key: string, method = "POST") =>
  request(path, method, body, { "Idempotency-Key": key });
export const ordersApi = {
  guest,
  config: () =>
    request("/orders/configuration").then((v) => {
      if (
        !record(v) ||
        ![
          v.max_active,
          v.max_portions,
          v.reservation_seconds,
          v.cutoff_minutes,
          v.slot_minutes,
          v.slot_capacity,
        ].every(isInteger)
      )
        return invalid();
      return v as OrderConfig;
    }),
  slots: (period: string, staff = false) =>
    request(
      `/orders/${staff ? "staff/" : ""}slots?period_id=${encodeURIComponent(period)}`,
    ).then((v) => list(v, slot)),
  saveSlot: (id: string | undefined, body: SlotInput, key: string) =>
    keyed(
      `/orders/staff/slots${id ? `/${id}` : ""}`,
      body,
      key,
      id ? "PUT" : "POST",
    ),
  checkout: async (body: CheckoutInput, key: string) => {
    await guest();
    return order(await keyed("/orders/checkout", body, key));
  },
  list: async (staff = false, offset = 0) => {
    if (!staff) await guest();
    return list(
      await request(
        `/orders${staff ? "/staff" : ""}?offset=${offset}&limit=20`,
      ),
      order,
    );
  },
  checkouts: async (offset = 0) => {
    await guest();
    return list(
      await request(`/orders/checkouts?offset=${offset}&limit=20`),
      order,
    );
  },
  transition: (id: string, body: KitchenTransition, key: string) =>
    keyed(`/orders/staff/${id}/transition`, body, key).then(order),
  cancel: (id: string) => request(`/orders/${id}/cancel`, "POST").then(order),
  pay: (id: string, outcome: "success" | "failed" | "timeout", key: string) =>
    keyed(`/orders/checkout/${id}/mock-payment`, { outcome }, key).then(order),
};
