import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { StaffManagement } from "../src/features/identity/StaffManagement";
import { identityApi, type Staff } from "../src/shared/api/identity";

const admin: Staff = {
  id: "1",
  login: "admin",
  name: "Әлия",
  phone: null,
  roles: ["admin"],
  is_demo: true,
  is_active: true,
  nickname: "",
  permissions: ["identity.manage"],
};
const cashier: Staff = {
  ...admin,
  id: "2",
  login: "kassir.01",
  name: "Айгерим",
  roles: ["cashier"],
};

afterEach(() => vi.restoreAllMocks());

it("администратор задаёт новый пароль сотруднику, забывшему свой", async () => {
  vi.spyOn(identityApi, "listStaff").mockResolvedValue([admin, cashier]);
  vi.spyOn(identityApi, "listRoles").mockResolvedValue([]);
  vi.spyOn(identityApi, "member").mockResolvedValue(cashier);
  const reset = vi
    .spyOn(identityApi, "resetPassword")
    .mockResolvedValue(cashier);
  render(<StaffManagement current={admin} onExpired={() => {}} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Изменить: Айгерим" }),
  );
  expect(screen.getByRole("form", { name: "Сброс пароля" })).toBeVisible();
  const field = screen.getByLabelText("Новый пароль");
  await userEvent.type(field, "abc");
  await userEvent.click(
    screen.getByRole("button", { name: "Сбросить пароль" }),
  );
  expect(reset).not.toHaveBeenCalled();
  expect(field).toHaveAttribute("aria-invalid", "true");
  await userEvent.clear(field);
  await userEvent.type(field, "Новый-пароль-2026");
  await userEvent.click(
    screen.getByRole("button", { name: "Сбросить пароль" }),
  );
  expect(reset).toHaveBeenCalledWith("2", "Новый-пароль-2026");
  expect(await screen.findByText(/Пароль изменён/)).toBeInTheDocument();
  expect(field).toHaveValue("");
});

it("свой пароль администратор в карточке не сбрасывает", async () => {
  vi.spyOn(identityApi, "listStaff").mockResolvedValue([admin]);
  vi.spyOn(identityApi, "listRoles").mockResolvedValue([]);
  vi.spyOn(identityApi, "member").mockResolvedValue(admin);
  render(<StaffManagement current={admin} onExpired={() => {}} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Изменить: Әлия" }),
  );
  expect(
    screen.queryByRole("form", { name: "Сброс пароля" }),
  ).not.toBeInTheDocument();
});
