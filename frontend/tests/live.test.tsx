import { afterEach, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KitchenLive } from "../src/features/orders/KitchenLive";
import { GuestLive } from "../src/features/orders/GuestLive";

class FakeSocket {
  static last: FakeSocket | null = null;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: unknown }) => void) | null = null;
  onclose: ((c: { code: number }) => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeSocket.last = this;
  }
  close() {
    this.closed = true;
  }
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  FakeSocket.last = null;
});

it("новый оплаченный заказ сразу перезагружает список и показывает сигнал", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("WebSocket", FakeSocket);
  const reload = vi.fn();
  render(<KitchenLive onReload={reload} />);
  const socket = FakeSocket.last!;
  expect(socket.url).toMatch(/^ws:\/\/.+\/api\/v1\/staff\/events$/);
  expect(screen.getByRole("status")).toHaveTextContent("Подключаемся");
  act(() => socket.onopen?.());
  expect(screen.getByRole("status")).toHaveTextContent("Обновляется сразу");
  await act(() => vi.advanceTimersByTimeAsync(400));
  expect(reload).toHaveBeenCalledTimes(1);
  act(() => {
    socket.onmessage?.({
      data: JSON.stringify({
        topic: "orders",
        kind: "confirmed",
        id: "cae50fe2-d7b7-475f-b584-b62333a2f68d",
      }),
    });
    socket.onmessage?.({ data: '{"topic":"orders","kind":"preparing"}' });
    socket.onmessage?.({ data: "not json" });
  });
  await act(() => vi.advanceTimersByTimeAsync(400));
  // A burst of signals becomes one reload.
  expect(reload).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("alert")).toHaveTextContent(/Новый заказ №\d{4}/);
  await userEvent.click(screen.getByRole("button", { name: "Понятно" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("без связи переподключается и обновляет по таймеру", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("WebSocket", FakeSocket);
  const reload = vi.fn();
  const view = render(<KitchenLive onReload={reload} />);
  const first = FakeSocket.last!;
  act(() => first.onclose?.({ code: 1006 }));
  expect(screen.getByRole("status")).toHaveTextContent("Нет связи");
  await act(() => vi.advanceTimersByTimeAsync(1100));
  expect(FakeSocket.last).not.toBe(first);
  await act(() => vi.advanceTimersByTimeAsync(15_000));
  expect(reload).toHaveBeenCalled();
  const second = FakeSocket.last!;
  view.unmount();
  expect(second.closed).toBe(true);
});

it("гость сразу видит, что заказ готов, по своему каналу", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("WebSocket", FakeSocket);
  const reload = vi.fn();
  render(<GuestLive onReload={reload} />);
  const socket = FakeSocket.last!;
  expect(socket.url).toMatch(/\/api\/v1\/orders\/live$/);
  act(() => socket.onopen?.());
  act(() =>
    socket.onmessage?.({
      data: JSON.stringify({
        topic: "orders",
        kind: "ready",
        id: "cae50fe2-d7b7-475f-b584-b62333a2f68d",
      }),
    }),
  );
  await act(() => vi.advanceTimersByTimeAsync(400));
  expect(reload).toHaveBeenCalled();
  expect(screen.getByRole("status")).toHaveTextContent(/готов! Покажите QR/);
});
