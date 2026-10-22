import { receivingApi } from "../src/shared/api/receiving";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PosBoard } from "../src/features/pos/PosBoard";
import { posApi, sale, type Sale } from "../src/shared/api/pos";
import { ApiError } from "../src/shared/api/http";
import type { PublicEntry } from "../src/shared/api/catalog";
const entry: PublicEntry = {
  id: "entry",
  period_id: "period",
  period_name: "Обед",
  name: "Плов",
  unit: "portion",
  category: "Горячее",
  description: "",
  portion_label: "250 г",
  price_minor: 12345,
  image_url: "",
  available: 2,
  starts_at: "2026-10-21T05:00:00Z",
  ends_at: "2026-10-21T15:00:00Z",
};
const receipt: Sale = {
  payment_method_name: "Наличные",
  id: "sale",
  actor_id: "cashier",
  outcome: "success",
  mode: "mock",
  currency: "KZT",
  returned_minor: 0,
  total_minor: 12345,
  created_at: "2026-10-21T07:00:00Z",
  lines: [
    {
      entry_id: "entry",
      name: "Плов",
      unit: "portion",
      portion_label: "250 г",
      quantity: 1,
      price_minor: 12345,
    },
  ],
};
const expire = vi.fn();
beforeEach(() => {
  sessionStorage.clear();
  vi.spyOn(receivingApi, "paymentMethods").mockResolvedValue([
    {
      id: "00000000-0000-0000-0000-000000000002",
      name: "Наличные",
      kind: "payment_method",
      commission_bp: 0,
    },
  ]);
  vi.spyOn(posApi, "menu").mockResolvedValue([entry]);
  vi.spyOn(posApi, "history").mockResolvedValue([]);
});
afterEach(() => vi.restoreAllMocks());
async function checkout() {
  await userEvent.click(
    await screen.findByRole("button", { name: "Добавить" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Перейти к оплате" }),
  );
}
it("потерянный ответ сохраняет ключ после reload и блокирует новую продажу", async () => {
  const send = vi
    .spyOn(posApi, "sell")
    .mockRejectedValueOnce(new ApiError(0, "Нет связи"))
    .mockResolvedValueOnce(receipt);
  const view = render(<PosBoard userId="cashier" onExpired={expire} />);
  await checkout();
  await userEvent.click(
    screen.getByRole("button", { name: "Оплата и выдача: успешно" }),
  );
  await within(screen.getByRole("dialog")).findByRole("button", {
    name: "Проверить результат / повторить",
  });
  expect(screen.getByRole("button", { name: "Добавить" })).toBeDisabled();
  const first = send.mock.calls[0];
  view.unmount();
  render(<PosBoard userId="cashier" onExpired={expire} />);
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(
    within(dialog).getByRole("button", {
      name: "Проверить результат / повторить",
    }),
  );
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(send.mock.calls[1]).toEqual(first);
  expect(sessionStorage.getItem("ashana.pos.pending.cashier")).toBeNull();
  expect(await screen.findByText(/Выдано ·/)).toBeInTheDocument();
});
it("отказ оставляет корзину, новая попытка имеет другой ключ; количество проверяется", async () => {
  const send = vi
    .spyOn(posApi, "sell")
    .mockResolvedValueOnce({ ...receipt, outcome: "failed" })
    .mockResolvedValueOnce(receipt);
  render(<PosBoard userId="cashier" onExpired={expire} />);
  await checkout();
  await userEvent.click(
    screen.getByRole("button", { name: "Оплата и выдача: успешно" }),
  );
  await screen.findByText(/Оплата отклонена ·/);
  const count = screen.getByLabelText("Плов");
  await userEvent.clear(count);
  await userEvent.type(count, "1e2");
  expect(
    screen.getByRole("button", { name: "Перейти к оплате" }),
  ).toBeDisabled();
  await userEvent.clear(count);
  await userEvent.type(count, "1");
  await userEvent.click(
    screen.getByRole("button", { name: "Перейти к оплате" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Оплата и выдача: успешно" }),
  );
  await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
  expect(send.mock.calls[0]![1]).not.toBe(send.mock.calls[1]![1]);
});
it("контракт кассы отвергает реальные деньги и некорректные строки", () => {
  expect(sale(receipt)).toEqual(receipt);
  expect(() => sale({ ...receipt, mode: "real" })).toThrow();
  expect(() =>
    sale({ ...receipt, lines: [{ ...receipt.lines[0], quantity: -1 }] }),
  ).toThrow();
});
it("истечение сессии не теряет ключ уже отправленной операции", async () => {
  sessionStorage.setItem(
    "ashana.pos.pending.cashier",
    JSON.stringify({
      key: "same-key",
      body: {
        outcome: "success",
        lines: [
          { entry_id: "entry", quantity: 1, expected_price_minor: 12345 },
        ],
      },
    }),
  );
  vi.spyOn(posApi, "sell").mockRejectedValueOnce(
    new ApiError(401, "Войдите снова"),
  );
  const expired = vi.fn();
  render(<PosBoard userId="cashier" onExpired={expired} />);
  await userEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "Проверить результат / повторить",
    }),
  );
  await waitFor(() => expect(expired).toHaveBeenCalledOnce());
  expect(
    JSON.parse(sessionStorage.getItem("ashana.pos.pending.cashier")!).key,
  ).toBe("same-key");
});
