import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ordersApi, type Order } from "../src/shared/api/orders";
import { OrderCard } from "../src/features/orders/OrderList";
import { PickupScanner } from "../src/features/orders/PickupScanner";
import {
  orderNumber,
  parsePickupPayload,
  pickupPayload,
} from "../src/shared/lib/pickup-qr";

const id = "cae50fe2-d7b7-475f-b584-b62333a2f68d";
const order: Order = {
  id,
  slot_id: "slot",
  status: "ready",
  stock_issue: false,
  total_minor: 280000,
  currency: "KZT",
  expires_at: "2026-10-22T18:05:00Z",
  created_at: "2026-10-22T18:00:00Z",
  updated_at: "2026-10-22T18:00:00Z",
  version: 3,
  slot_starts_at: "2026-10-22T18:10:00Z",
  slot_ends_at: "2026-10-22T18:20:00Z",
  dining: "here",
  pickup_code: "981E69F1",
  lines: [
    {
      entry_id: "entry",
      name: "Плов с говядиной",
      portion_label: "350 г",
      unit: "portion",
      quantity: 1,
      price_minor: 160000,
    },
  ],
};
afterEach(() => vi.restoreAllMocks());

describe("QR-код получения", () => {
  it("кодирует и строго разбирает payload", () => {
    const payload = pickupPayload(id, "981E69F1");
    expect(parsePickupPayload(payload)).toEqual({
      orderId: id,
      code: "981E69F1",
    });
    expect(parsePickupPayload(` ${payload.toLowerCase()} `)).toEqual({
      orderId: id,
      code: "981E69F1",
    });
    expect(parsePickupPayload("981E69F1")).toBeNull();
    expect(parsePickupPayload(`ASHANA1:${id}:981E69F`)).toBeNull();
    expect(parsePickupPayload(`OTHER:${id}:981E69F1`)).toBeNull();
    expect(parsePickupPayload(`${payload}:extra`)).toBeNull();
    expect(orderNumber(id)).toMatch(/^\d{4}$/);
  });

  it("гость видит QR и код только для активного заказа", () => {
    const { rerender } = render(
      <OrderCard order={order} staff={false} onChanged={vi.fn()} />,
    );
    expect(
      screen.getByRole("img", { name: /QR-код заказа №/ }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("pickup-code")).toHaveTextContent("981E69F1");
    rerender(
      <OrderCard
        order={{ ...order, status: "completed" }}
        staff={false}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.queryByRole("img", { name: /QR-код/ })).toBeNull();
    rerender(<OrderCard order={order} staff onChanged={vi.fn()} />);
    expect(screen.queryByRole("img", { name: /QR-код/ })).toBeNull();
  });

  it("сканер находит заказ и выдаёт его с кодом из QR", async () => {
    const lookup = vi.spyOn(ordersApi, "staffOrder").mockResolvedValue(order);
    const transition = vi
      .spyOn(ordersApi, "transition")
      .mockResolvedValue({ ...order, status: "completed" });
    render(<PickupScanner permissions={["kitchen.read", "orders.fulfil"]} />);
    await userEvent.type(
      screen.getByLabelText("Ручной сканер или вставка данных"),
      `${pickupPayload(id, "981E69F1")}{Enter}`,
    );
    await waitFor(() => expect(lookup).toHaveBeenCalledWith(id));
    await userEvent.click(
      await screen.findByRole("button", { name: "Выдать заказ" }),
    );
    await waitFor(() => expect(transition).toHaveBeenCalledOnce());
    expect(transition.mock.calls[0]?.[1]).toEqual({
      target: "completed",
      expected_version: 3,
      pickup_code: "981E69F1",
    });
    expect(await screen.findByText(/выдан$/)).toBeInTheDocument();
  });

  it("сканер отклоняет чужой QR и не выдаёт без права", async () => {
    const lookup = vi.spyOn(ordersApi, "staffOrder").mockResolvedValue(order);
    render(<PickupScanner permissions={["kitchen.read"]} />);
    const field = screen.getByLabelText("Ручной сканер или вставка данных");
    await userEvent.type(field, "https://example.com{Enter}");
    expect(
      await screen.findByText(/Это не QR-код заказа AsHana/),
    ).toBeInTheDocument();
    expect(lookup).not.toHaveBeenCalled();
    await userEvent.type(field, `${pickupPayload(id, "981E69F1")}{Enter}`);
    expect(
      await screen.findByText(/Выдачу подтверждает кассир/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Выдать заказ" }),
    ).not.toBeInTheDocument();
  });
});
