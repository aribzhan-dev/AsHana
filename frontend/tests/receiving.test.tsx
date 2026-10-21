import { afterEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReceivingBoard } from "../src/features/receiving/ReceivingBoard";
import { receivingApi } from "../src/shared/api/receiving";
import { inventoryApi } from "../src/shared/api/inventory";
afterEach(() => vi.restoreAllMocks());
it("накладная отправляет строки и расходы целиком и закрывается после подтверждения", async () => {
  vi.spyOn(inventoryApi, "items").mockResolvedValue([
    { id: "rice", name: "Рис", kind: "raw", unit: "kg" },
  ]);
  vi.spyOn(receivingApi, "invoices").mockResolvedValue([]);
  vi.spyOn(receivingApi, "directories").mockImplementation(async (kind) => [
    {
      kind,
      id:
        kind === "supplier"
          ? "supplier"
          : kind === "warehouse"
            ? "00000000-0000-0000-0000-000000000001"
            : "00000000-0000-0000-0000-000000000002",
      name: kind,
    },
  ]);
  const save = vi
    .spyOn(receivingApi, "receive")
    .mockResolvedValue({ subject_id: "invoice", version: 1 });
  render(<ReceivingBoard onExpired={() => undefined} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Новая накладная" }),
  );
  await userEvent.type(screen.getByLabelText("Номер накладной"), "123");
  await userEvent.selectOptions(screen.getByLabelText("Поставщик"), "supplier");
  await userEvent.selectOptions(screen.getByLabelText("Товар 1"), "rice");
  await userEvent.type(screen.getByLabelText("Количество, кг"), "1,25");
  await userEvent.type(screen.getByLabelText("Цена за единицу, ₸"), "98,76");
  const expiry = screen.getByLabelText("Годен до (Астана)");
  await userEvent.type(expiry, "2026-12-20T12:00");
  await userEvent.click(
    screen.getByRole("button", { name: "Провести приход" }),
  );
  await waitFor(() => expect(save).toHaveBeenCalledOnce());
  expect(save.mock.calls[0]![0].lines[0]).toMatchObject({
    item_id: "rice",
    quantity: "1.25",
    unit_cost_minor: 9876,
  });
  expect(
    await screen.findByRole("button", { name: "Новая накладная" }),
  ).toBeVisible();
});
