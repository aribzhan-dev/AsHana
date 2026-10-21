import { afterEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  costMinor,
  stockQuantityError,
  almatyInstant,
  decimalText,
} from "../src/shared/lib/inventory-validation";
import { inventoryApi } from "../src/shared/api/inventory";
import { ApiError } from "../src/shared/api/http";
import { ItemForm, ReceiptForm } from "../src/features/inventory/StockForms";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("количество и деньги не принимают экспоненту и скрытое округление", () => {
  for (const value of ["NaN", "Infinity", "1e3", "1.0001", "-1", "0", "１２"])
    expect(stockQuantityError(value, "kg")).toBeTruthy();
  expect(stockQuantityError("1,25", "kg")).toBeUndefined();
  expect(stockQuantityError("0", "kg", true)).toBeUndefined();
  expect(stockQuantityError("0.5", "pcs")).toBeTruthy();
  expect(stockQuantityError("999999999000", "g")).toBeUndefined();
  expect(stockQuantityError("999999999001", "g")).toBeTruthy();
  expect(costMinor("12,34")).toBe(1234);
  expect(costMinor("9999999999.99")).toBe(999999999999);
  for (const value of ["1.001", "NaN", "1e2", "-1", "10000000000"])
    expect(costMinor(value)).toBeUndefined();
  expect(decimalText(" 1,20 ")).toBe("1.20");
});
it("Астана сохраняется как UTC независимо от зоны браузера", () => {
  expect(almatyInstant("2026-10-21T12:30")).toBe("2026-10-21T07:30:00.000Z");
  expect(almatyInstant("2026-02-30T12:30")).toBeUndefined();
  expect(almatyInstant("не дата")).toBeUndefined();
});
it("невалидный контракт склада не отображается как достоверный остаток", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify([{ id: "id", on_hand: "NaN" }])),
      ),
  );
  await expect(inventoryApi.batches()).rejects.toThrow(
    "Не удалось получить данные склада",
  );
});
it("изменение передаёт CSRF и ключ идемпотентности", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ csrf_token: "synthetic" })),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ subject_id: "id", version: 1 })),
    );
  vi.stubGlobal("fetch", fetchMock);
  await inventoryApi.createItem(
    {
      name: "Рис",
      kind: "raw",
      category: "",
      purchase_price_minor: 0,
      sale_price_minor: 0,
      unit: "kg",
    },
    "request-key",
  );
  expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/v1/inventory/items",
    expect.objectContaining({
      headers: expect.objectContaining({
        "Idempotency-Key": "request-key",
        "X-CSRF-Token": "synthetic",
      }),
    }),
  );
});
it("повтор после потери ответа использует тот же ключ и сохраняет ввод", async () => {
  const create = vi
    .spyOn(inventoryApi, "createItem")
    .mockRejectedValueOnce(new ApiError(0, "Ошибка сети"))
    .mockResolvedValueOnce({ subject_id: "id", version: 1 });
  const saved = vi.fn();
  render(<ItemForm onExpired={vi.fn()} onSaved={saved} />);
  await userEvent.type(screen.getByLabelText("Название"), "Рис");
  await userEvent.click(screen.getByRole("button", { name: "Создать товар" }));
  expect(
    await screen.findByText(
      "Ответ не получен. Проверьте историю или повторите отправку без изменения данных.",
    ),
  ).toBeVisible();
  expect(screen.getByLabelText("Название")).toHaveValue("Рис");
  await userEvent.click(screen.getByRole("button", { name: "Создать товар" }));
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(create.mock.calls[0]?.[1]).toBe(create.mock.calls[1]?.[1]);
  expect(screen.getByLabelText("Название")).toHaveValue("");
});
it("приход собственной продукции недоступен, ошибка количества связана с полем", async () => {
  const { rerender } = render(
    <ReceiptForm
      items={[
        {
          id: "a",
          name: "Каша",
          kind: "prepared",
          category: "",
          purchase_price_minor: 0,
          sale_price_minor: 0,
          version: 1,
          unit: "portion",
        },
      ]}
      onExpired={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  expect(
    screen.getByText("Добавьте сырьё или покупной товар для прихода"),
  ).toBeVisible();
  rerender(
    <ReceiptForm
      items={[
        {
          id: "b",
          name: "Рис",
          kind: "raw",
          category: "",
          purchase_price_minor: 0,
          sale_price_minor: 0,
          version: 1,
          unit: "kg",
        },
      ]}
      onExpired={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await userEvent.type(screen.getByLabelText("Количество"), "1e3");
  await userEvent.click(
    screen.getByRole("button", { name: "Оформить приход" }),
  );
  expect(screen.getByLabelText("Количество")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(screen.getByLabelText("Количество")).toHaveAccessibleDescription(
    expect.stringContaining("Введите корректное количество"),
  );
});
