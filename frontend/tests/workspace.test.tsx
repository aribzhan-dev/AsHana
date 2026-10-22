import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Dashboard } from "../src/features/reporting/Dashboard";
import { StaffNavigation } from "../src/shared/ui/StaffNavigation";
import { reportsApi } from "../src/shared/api/reporting";
import type { Staff } from "../src/shared/api/identity";
const user: Staff = {
  id: "1",
  login: "manager",
  name: "Айша",
  phone: null,
  roles: ["manager"],
  is_demo: true,
  nickname: "",
  permissions: ["reporting.read", "pos.sell"],
};
it("обзор показывает точные суммы и нулевые продажи, сессии отсутствуют", async () => {
  vi.spyOn(reportsApi, "dashboard").mockResolvedValue({
    generated_at: "2026-10-21T12:00:00Z",
    hours: [],
    totals: {
      paid_minor: "90071992547409931",
      issued_minor: "100",
      refund_minor: "0",
      products: "1",
    },
    top: [{ id: "a", name: "Плов", quantity: "12" }],
    low: [{ id: "b", name: "Суп", quantity: "0" }],
  });
  render(<Dashboard user={user} onExpired={vi.fn()} />);
  expect(
    await screen.findByText(/900.*719.*925.*474.*099,31/),
  ).toBeInTheDocument();
  expect(screen.getByText("0 шт./порц.")).toBeInTheDocument();
  expect(screen.queryByText("Ваши сессии")).not.toBeInTheDocument();
  await userEvent.clear(screen.getByLabelText("По дату"));
  await userEvent.click(screen.getByRole("button", { name: "Применить" }));
  expect(
    screen.getByText("Выберите период от 1 до 366 дней."),
  ).toBeInTheDocument();
});
it("навигация следует разрешениям, а профиль доступен каждому", () => {
  render(<StaffNavigation user={user} />);
  expect(screen.getByRole("link", { name: "Касса" })).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Сотрудники и роли" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Мой профиль" })).toBeInTheDocument();
});
