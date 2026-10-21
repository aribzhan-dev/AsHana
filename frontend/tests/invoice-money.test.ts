import { expect, it } from "vitest";
import { invoiceLineCost } from "../src/shared/lib/invoice-money";
it("накладная считает дробное количество без ошибок двоичной арифметики", () => {
  expect(invoiceLineCost("1,255", "1,01")).toBe(127);
  expect(invoiceLineCost("0,5", "0,01")).toBe(1);
  expect(invoiceLineCost("3", "100,50")).toBe(30150);
  expect(invoiceLineCost("999999999", "9999999,99")).toBeUndefined();
  expect(invoiceLineCost("1e2", "10")).toBeUndefined();
  expect(invoiceLineCost("-1", "10")).toBeUndefined();
});
