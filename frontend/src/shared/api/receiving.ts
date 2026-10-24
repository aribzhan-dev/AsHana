import type { components } from "./schema";
import { request, record, ApiError } from "./http";
import { operation } from "./inventory";
export type Directory = components["schemas"]["DirectoryResponse"];
export type DirectoryKind = Directory["kind"];
export type DirectoryDetails =
  components["schemas"]["DirectoryDetailsResponse"];
export type PurchaseKind = Exclude<
  DirectoryKind,
  "category" | "expense_category"
>;
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
        ![
          "supplier",
          "warehouse",
          "payment_method",
          "category",
          "expense_category",
        ].includes(String(d.kind)),
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
  // Preview: the entry with the places that use it (invoices, sales, goods...).
  directory: (id: string) =>
    request(`/inventory/directories/${encodeURIComponent(id)}`).then((v) => {
      if (!record(v) || typeof v.name !== "string" || !record(v.usage))
        throw new ApiError(0, "Не удалось прочитать запись");
      return v as DirectoryDetails;
    }),
  renameDirectory: (id: string, name: string, key: string) =>
    request(
      `/inventory/directories/${encodeURIComponent(id)}`,
      "PUT",
      { name },
      { "Idempotency-Key": key },
    ).then(operation),
  deleteDirectory: (id: string, key: string) =>
    request(
      `/inventory/directories/${encodeURIComponent(id)}`,
      "DELETE",
      undefined,
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
  pay: (
    invoiceId: string,
    body: components["schemas"]["InvoicePaymentInput"],
    key: string,
  ) =>
    request(
      `/inventory/invoices/${encodeURIComponent(invoiceId)}/payments`,
      "POST",
      body,
      { "Idempotency-Key": key },
    ).then(operation),
  receive: (body: InvoiceInput, key: string) =>
    request("/inventory/invoices", "POST", body, {
      "Idempotency-Key": key,
    }).then(operation),
};
