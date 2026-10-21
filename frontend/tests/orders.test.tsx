import { afterEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ordersApi, type Order } from "../src/shared/api/orders";
import { ApiError } from "../src/shared/api/http";
import { OrderCard } from "../src/features/orders/OrderList";
const checkout: Order = {
  id: "00000000-0000-0000-0000-000000000001",
  slot_id: "slot",
  status: "pending_payment",
  stock_issue: false,
  total_minor: 12345,
  currency: "KZT",
  expires_at: "2026-10-21T10:05:00Z",
  created_at: "2026-10-21T10:00:00Z",
  updated_at: "2026-10-21T10:00:00Z",
  version: 1,
  slot_starts_at: "2026-10-21T12:00:00Z",
  slot_ends_at: "2026-10-21T12:10:00Z",
  lines: [
    {
      entry_id: "entry",
      name: "Плов",
      portion_label: "250 г",
      unit: "portion",
      quantity: 1,
      price_minor: 12345,
    },
  ],
};
afterEach(() => vi.restoreAllMocks());
it("оформление до оплаты отделено от заказа, повтор оплаты сохраняет ключ", async () => {
  const pay = vi
    .spyOn(ordersApi, "pay")
    .mockRejectedValueOnce(new ApiError(0, "Потерян ответ"))
    .mockResolvedValueOnce({ ...checkout, status: "confirmed" });
  const changed = vi.fn();
  render(<OrderCard order={checkout} staff={false} onChanged={changed} />);
  expect(
    screen.getByRole("heading", { name: /Оформление/ }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Это ещё не заказ/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Оплатить заказ" }));
  await screen.findByText(/Ответ не получен/);
  expect(changed).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Оплатить заказ" }));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(pay.mock.calls[0]?.[2]).toBe(pay.mock.calls[1]?.[2]);
});
it("отказ не показывает подтверждённый заказ", async () => {
  vi.spyOn(ordersApi, "pay").mockResolvedValue(checkout);
  render(<OrderCard order={checkout} staff={false} onChanged={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Оплатить заказ" }));
  await screen.findByText(/Оплата не подтверждена\. Можно/);
  expect(screen.queryByText("Принят")).not.toBeInTheDocument();
});
it("неверный денежный ответ заказа отклоняется", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify([{ ...checkout, total_minor: 1.5 }])),
      ),
  );
  await expect(ordersApi.list(true)).rejects.toThrow(
    "Не удалось получить данные заказов",
  );
});

it("комплектация доступна кухне и сохраняет ключ при потере ответа", async () => {
  const transition = vi
    .spyOn(ordersApi, "transition")
    .mockRejectedValueOnce(new ApiError(0, "Нет ответа"))
    .mockResolvedValueOnce({ ...checkout, status: "preparing" });
  const changed = vi.fn();
  render(
    <OrderCard
      order={{ ...checkout, status: "confirmed" }}
      staff
      permissions={["kitchen.manage"]}
      onChanged={changed}
    />,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Начать комплектацию" }),
  );
  await screen.findByText(/Ответ не получен/);
  await userEvent.click(
    screen.getByRole("button", { name: "Начать комплектацию" }),
  );
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(transition.mock.calls[0]?.[2]).toBe(transition.mock.calls[1]?.[2]);
});

it("выдача требует кода посетителя и подтверждения кассира", async () => {
  const transition = vi
    .spyOn(ordersApi, "transition")
    .mockResolvedValue({ ...checkout, status: "completed" });
  render(
    <OrderCard
      order={{ ...checkout, status: "ready" }}
      staff
      permissions={["orders.fulfil"]}
      onChanged={vi.fn()}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Выдать заказ" }));
  await userEvent.click(
    screen.getByRole("button", { name: "Подтвердить выдачу" }),
  );
  expect(transition).not.toHaveBeenCalled();
  await userEvent.type(screen.getByLabelText("Код получения"), "a12b34cd");
  await userEvent.click(
    screen.getByRole("button", { name: "Подтвердить выдачу" }),
  );
  await waitFor(() => expect(transition).toHaveBeenCalledOnce());
  expect(transition.mock.calls[0]?.[1]).toMatchObject({
    target: "completed",
    pickup_code: "A12B34CD",
  });
});

it("у кухни без права выдачи и у выданного заказа нет кнопки выдачи", () => {
  const { rerender } = render(
    <OrderCard
      order={{ ...checkout, status: "ready" }}
      staff
      permissions={["kitchen.manage"]}
      onChanged={vi.fn()}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "Выдать заказ" }),
  ).not.toBeInTheDocument();
  rerender(
    <OrderCard
      order={{ ...checkout, status: "completed" }}
      staff
      permissions={["orders.fulfil"]}
      onChanged={vi.fn()}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "Выдать заказ" }),
  ).not.toBeInTheDocument();
});
