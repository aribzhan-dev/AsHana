import { render, screen, within } from "@testing-library/react";
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
const cook: Staff = {
  ...admin,
  id: "2",
  login: "povar.01",
  name: "Ерлан",
  roles: ["kitchen"],
  phone: "+77010000022",
  telegram: "@erlan_k",
  created_at: "2026-10-20T05:00:00Z",
};

afterEach(() => vi.restoreAllMocks());

function setup() {
  vi.spyOn(identityApi, "listStaff").mockResolvedValue([admin, cook]);
  vi.spyOn(identityApi, "listRoles").mockResolvedValue([
    { code: "kitchen", name: "Повар", permissions: [], version: 1 },
  ]);
  vi.spyOn(identityApi, "member").mockResolvedValue(cook);
  render(<StaffManagement current={admin} onExpired={() => {}} />);
}

it("карточка сотрудника показывает контакты, роли и статус; блокировка", async () => {
  setup();
  const block = vi
    .spyOn(identityApi, "status")
    .mockResolvedValue({ ...cook, is_active: false });
  await userEvent.click(
    await screen.findByRole("button", { name: "Просмотр: Ерлан" }),
  );
  const card = screen.getByRole("dialog");
  expect(card).toHaveTextContent("+77010000022");
  expect(within(card).getByRole("link", { name: "@erlan_k" })).toHaveAttribute(
    "href",
    "https://t.me/erlan_k",
  );
  expect(card).toHaveTextContent("Повар");
  expect(card).toHaveTextContent("Активен");
  await userEvent.click(
    within(card).getByRole("button", { name: "Заблокировать" }),
  );
  expect(block).toHaveBeenCalledWith("2", false);
  expect(await within(card).findByText("Заблокирован")).toBeVisible();
  expect(
    within(card).getByRole("button", { name: "Разблокировать" }),
  ).toBeVisible();
});

it("администратор меняет телефон и Telegram; неверный ник не отправляется", async () => {
  setup();
  const save = vi
    .spyOn(identityApi, "profile")
    .mockResolvedValue({ ...cook, telegram: "@erlan_new" });
  await userEvent.click(
    await screen.findByRole("button", { name: "Изменить: Ерлан" }),
  );
  const form = screen.getByRole("form", { name: "Данные сотрудника" });
  const telegram = within(form).getByLabelText("Telegram");
  await userEvent.clear(telegram);
  await userEvent.type(telegram, "@ab");
  await userEvent.click(
    within(form).getByRole("button", { name: "Сохранить данные" }),
  );
  expect(save).not.toHaveBeenCalled();
  expect(telegram).toHaveAttribute("aria-invalid", "true");
  await userEvent.clear(telegram);
  await userEvent.type(telegram, "erlan_new");
  await userEvent.click(
    within(form).getByRole("button", { name: "Сохранить данные" }),
  );
  expect(save).toHaveBeenCalledWith("2", {
    name: "Ерлан",
    nickname: "",
    phone: "+77010000022",
    telegram: "erlan_new",
  });
  expect(await within(form).findByText("Данные сохранены")).toBeVisible();
});

it("удаление с подтверждением; себя удалить нельзя", async () => {
  setup();
  const remove = vi.spyOn(identityApi, "remove").mockResolvedValue();
  expect(
    await screen.findByRole("button", { name: "Удалить: Әлия" }),
  ).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Удалить: Ерлан" }));
  const dialog = screen.getByRole("dialog");
  expect(dialog).toHaveTextContent("не сможет войти");
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Удалить" }),
  );
  expect(remove).toHaveBeenCalledWith("2");
});
