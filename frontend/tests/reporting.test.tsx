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
it("отчёт открывается из меню, даты проверяются до запроса", async () => {
  window.location.hash = "#sales";
  vi.spyOn(reportsApi, "options").mockResolvedValue([]);
  const load = vi.spyOn(reportsApi, "read").mockResolvedValue(data);
  render(<ReportBoard onExpired={vi.fn()} />);
  expect(await screen.findByRole("cell", { name: "Плов" })).toBeInTheDocument();
  expect(screen.getAllByText("123,45 ₸").length).toBeGreaterThan(0);
  const calls = load.mock.calls.length;
  const end = screen.getByLabelText("По дату включительно");
  await userEvent.clear(end);
  await userEvent.type(end, "2000-01-01");
  await screen.findByText(/Укажите корректные даты/);
  expect(load).toHaveBeenCalledTimes(calls);
  await userEvent.click(screen.getByRole("button", { name: "7 дней" }));
  await userEvent.click(screen.getByRole("button", { name: "ABC-анализ" }));
  await waitFor(() => expect(load.mock.lastCall?.[0]).toBe("abc"));
});
it("остатки и долги не зависят от дат", async () => {
  window.location.hash = "#stock";
  vi.spyOn(reportsApi, "options").mockResolvedValue([]);
  vi.spyOn(reportsApi, "read").mockResolvedValue({ ...data, kind: "stock" });
  render(<ReportBoard onExpired={vi.fn()} />);
  await screen.findByRole("cell", { name: "Плов" });
  expect(screen.queryByLabelText("С даты (Астана)")).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Долги поставщикам" }),
  );
  expect(screen.queryByLabelText("С даты (Астана)")).not.toBeInTheDocument();
});
