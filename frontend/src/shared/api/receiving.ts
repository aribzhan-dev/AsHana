import type { components } from "./schema";
import { request, record, ApiError } from "./http";
import { operation } from "./inventory";
export type Directory = components["schemas"]["DirectoryResponse"];
export type DirectoryKind = Directory["kind"];
export type Invoice = components["schemas"]["InvoiceResponse"];
export type InvoiceInput = components["schemas"]["InvoiceInput"];
function directories(value: unknown): Directory[] {
  if (
    !Array.isArray(value) ||
    value.some(
      (d) =>
        !record(d) ||
        typeof d.id !== "string" ||
        typeof d.name !== "string" ||
        !["supplier", "warehouse", "payment_method"].includes(String(d.kind)),
    )
  )
    throw new ApiError(0, "Не удалось прочитать справочник");
  return value as Directory[];
}
export const receivingApi = {
  directories: (kind: DirectoryKind) =>
    request(`/inventory/directories?kind=${kind}`).then(directories),
  paymentMethods: () => request("/pos/payment-methods").then(directories),
  createDirectory: (kind: DirectoryKind, name: string, key: string) =>
    request(
      "/inventory/directories",
      "POST",
      { kind, name },
      { "Idempotency-Key": key },
    ).then(operation),
  invoices: (offset = 0) =>
    request(`/inventory/invoices?offset=${offset}&limit=20`).then((value) => {
      if (
        !Array.isArray(value) ||
        value.some(
          (i) =>
            !record(i) ||
            typeof i.id !== "string" ||
            typeof i.number !== "string" ||
            !Array.isArray(i.lines) ||
            !Number.isSafeInteger(i.total_minor),
        )
      )
        throw new ApiError(0, "Не удалось прочитать накладные");
      return value as Invoice[];
    }),
  receive: (body: InvoiceInput, key: string) =>
    request("/inventory/invoices", "POST", body, {
      "Idempotency-Key": key,
    }).then(operation),
};
