import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { Directories } from "../src/features/receiving/Directories";
import { receivingApi, type Directory } from "../src/shared/api/receiving";

const cash: Directory = {
  id: "00000000-0000-0000-0000-000000000002",
  kind: "payment_method",
  name: "Наличные",
  commission_bp: 0,
  system: false,
};
const spare: Directory = { ...cash, id: "spare", name: "Перевод" };
const online: Directory = {
  ...cash,
  id: "00000000-0000-0000-0000-000000000004",
  name: "Онлайн-оплата",
  system: true,
};
const operation = { subject_id: "x", version: 1 };

afterEach(() => vi.restoreAllMocks());

it("используемую запись можно посмотреть и переименовать, но не удалить", async () => {
  vi.spyOn(receivingApi, "directories").mockResolvedValue([
    cash,
    spare,
    online,
  ]);
  vi.spyOn(receivingApi, "directory").mockResolvedValue({
    ...cash,
    usage: { "Продажи на кассе": 12 },
  });
  const rename = vi
    .spyOn(receivingApi, "renameDirectory")
    .mockResolvedValue(operation);
  render(<Directories onExpired={() => {}} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Просмотр: Наличные" }),
  );
  const dialog = screen.getByRole("dialog");
  expect(await within(dialog).findByText("Продажи на кассе")).toBeVisible();
  expect(within(dialog).getByText("12")).toBeVisible();
  expect(
    within(dialog).getByRole("button", { name: "Удалить" }),
  ).toBeDisabled();
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Изменить" }),
  );
  const field = within(dialog).getByLabelText(/Название/);
  await userEvent.clear(field);
  await userEvent.type(field, "Наличные (касса)");
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Сохранить" }),
  );
  expect(rename).toHaveBeenCalledWith(
    cash.id,
    "Наличные (касса)",
    expect.any(String),
  );
  // A system entry cannot even start the delete flow.
  expect(
    screen.getByRole("button", { name: "Удалить: Онлайн-оплата" }),
  ).toBeDisabled();
});

it("неиспользуемую запись удаляют после подтверждения", async () => {
  vi.spyOn(receivingApi, "directories").mockResolvedValue([spare]);
  vi.spyOn(receivingApi, "directory").mockResolvedValue({
    ...spare,
    usage: {},
  });
  const remove = vi
    .spyOn(receivingApi, "deleteDirectory")
    .mockResolvedValue(operation);
  render(<Directories onExpired={() => {}} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Удалить: Перевод" }),
  );
  const dialog = screen.getByRole("dialog");
  expect(
    await within(dialog).findByText(/нигде не используется/),
  ).toBeVisible();
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Удалить" }),
  );
  expect(remove).toHaveBeenCalledWith("spare", expect.any(String));
});
