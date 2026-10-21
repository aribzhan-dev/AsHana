import { afterEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportBoard } from "../src/features/reporting/ReportBoard";
import {
  reportsApi,
  reportValue,
  parseReport,
  type Report,
} from "../src/shared/api/reporting";
const data: Report = {
  kind: "sales",
  generated_at: "2026-10-21T10:00:00Z",
  columns: [
    { key: "name", label: "Товар", format: "text" },
    { key: "paid_minor", label: "Поступления", format: "money" },
  ],
  rows: [{ name: "Плов", paid_minor: "12345" }],
  totals: { paid_minor: "12345" },
  unit_totals: {},
  total_rows: 1,
  offset: 0,
  limit: 20,
  note: "ДЕМО",
};
afterEach(() => vi.restoreAllMocks());
it("суммы отчёта не теряют тиыны выше безопасного integer JS", () => {
  expect(reportValue("900719925474099301", "money")).toContain(",01 ₸");
  expect(reportValue("1.125000", "quantity")).toBe("1,125");
  expect(parseReport(data)).toEqual(data);
  expect(() =>
    parseReport({ ...data, totals: { paid_minor: "1.5" } }),
  ).toThrow();
});
it("режим и даты применяются явно; ошибочный диапазон не отправляется", async () => {
  vi.spyOn(reportsApi, "options").mockResolvedValue([]);
  const load = vi.spyOn(reportsApi, "read").mockResolvedValue(data);
  render(<ReportBoard onExpired={vi.fn()} />);
  await screen.findByText("Плов");
  await userEvent.selectOptions(screen.getByLabelText("Режим оплаты"), "real");
  expect(load).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole("button", { name: "Показать отчёт" }));
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  expect(load.mock.calls[1]![1].mode).toBe("real");
  const end = screen.getByLabelText("По дату включительно");
  await userEvent.clear(end);
  await userEvent.click(screen.getByRole("button", { name: "Показать отчёт" }));
  expect(load).toHaveBeenCalledTimes(2);
  await screen.findByText(/Укажите корректные даты/);
});
it("остаток обозначен текущим; даты и денежные фильтры отключены", async () => {
  vi.spyOn(reportsApi, "options").mockResolvedValue([]);
  vi.spyOn(reportsApi, "read").mockResolvedValue(data);
  render(<ReportBoard onExpired={vi.fn()} />);
  await screen.findByText("Плов");
  await userEvent.selectOptions(screen.getByLabelText("Вид отчёта"), "stock");
  expect(screen.getByLabelText("С даты (Астана)")).toBeDisabled();
  expect(screen.queryByLabelText("Режим оплаты")).not.toBeInTheDocument();
});
