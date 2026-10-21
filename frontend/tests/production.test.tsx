import { afterEach, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../src/shared/api/http";
import { productionApi, type Recipe } from "../src/shared/api/production";
import {
  editableRaw,
  wholeError,
} from "../src/shared/lib/production-validation";
import { RecipeForm } from "../src/features/production/RecipeForm";
import { ProductionForm } from "../src/features/production/ProductionForm";

const recipe: Recipe = {
  id: "recipe",
  output_item_id: "output",
  output_name: "Каша",
  output_unit: "portion",
  version: 3,
  expected_yield: 12,
  portion_quantity: "0.250125",
  portion_unit: "kg",
  instructions: "Сварить",
  actor_id: "actor",
  created_at: "2026-10-21T07:30:00Z",
  lines: [
    { item_id: "rice", item_name: "Рис", quantity: "1.000125", unit: "kg" },
  ],
};
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("точность старой версии сохраняется при редактировании в граммах", () => {
  expect(editableRaw("999999999.000000", "kg")).toEqual({
    quantity: "999999999000.000",
    unit: "g",
  });
  expect(editableRaw("0.000001", "l")).toEqual({
    quantity: "0.001",
    unit: "ml",
  });
  for (const value of ["0", "-1", "1.5", "1e3", "１２", "1000000000"])
    expect(wholeError(value)).toBeTruthy();
  expect(wholeError("12")).toBe("");
});
it("новая версия отправляет прежнюю версию и точные нормы, не изменяя старую", async () => {
  vi.spyOn(productionApi, "items").mockResolvedValue([]);
  const create = vi
    .spyOn(productionApi, "createRecipe")
    .mockResolvedValue({ subject_id: "new", version: 4 });
  const saved = vi.fn();
  render(
    <RecipeForm
      previous={recipe}
      onSaved={saved}
      onExpired={vi.fn()}
      onBusy={vi.fn()}
    />,
  );
  await screen.findByLabelText("Плановый выход");
  expect(
    screen.getByLabelText("Размер одной готовой порции / изделия"),
  ).toHaveValue("250.125");
  expect(screen.getByLabelText("Норма на весь плановый выпуск")).toHaveValue(
    "1000.125",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить версию" }),
  );
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(create).toHaveBeenCalledWith(
    expect.objectContaining({
      previous_version: 3,
      portion_quantity: "250.125",
      portion_unit: "g",
      lines: [{ item_id: "rice", quantity: "1000.125", unit: "g" }],
    }),
    expect.any(String),
  );
  expect(recipe.version).toBe(3);
});
it("неполный и повреждённый ответ производства отклоняется", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify([{ ...recipe, expected_yield: 1.5 }])),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify([
          {
            ...recipe,
            lines: [
              {
                item_id: "rice",
                item_name: "Рис",
                quantity: "NaN",
                unit: "kg",
              },
            ],
          },
        ]),
      ),
    );
  vi.stubGlobal("fetch", fetch);
  await expect(productionApi.recipes()).rejects.toThrow(
    "Не удалось получить данные производства",
  );
  await expect(productionApi.recipes()).rejects.toThrow(
    "Не удалось получить данные производства",
  );
});
it("выпуск требует подтверждения и целого выхода; повтор сохраняет ключ и фактический расход", async () => {
  vi.spyOn(productionApi, "batches").mockResolvedValue([
    {
      id: "batch",
      item_id: "rice",
      item_name: "Рис",
      label: "Поставка",
      unit: "kg",
      available: "2.000000",
      status: "active",
      expires_at: "2099-01-01T00:00:00Z",
    },
  ]);
  const produce = vi
    .spyOn(productionApi, "produce")
    .mockRejectedValueOnce(new ApiError(0, "Потерян ответ"))
    .mockResolvedValueOnce({ subject_id: "finished", version: 1 });
  const saved = vi.fn();
  render(
    <ProductionForm
      recipe={recipe}
      onSaved={saved}
      onExpired={vi.fn()}
      onBusy={vi.fn()}
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Подтвердить выпуск" }),
    ).toBeEnabled(),
  );
  await userEvent.selectOptions(
    screen.getByLabelText("Партия сырья 1"),
    "batch",
  );
  await userEvent.type(screen.getByLabelText("Фактический расход"), "0,75");
  await userEvent.type(screen.getByLabelText("Обозначение партии"), "Утро");
  await userEvent.type(screen.getByLabelText("Фактический выход"), "10");
  const expiry = screen.getByLabelText("Годна до (Алматы)");
  await userEvent.type(expiry, "2098-01-01T12:00");
  await userEvent.click(
    screen.getByRole("button", { name: "Подтвердить выпуск" }),
  );
  expect(produce).not.toHaveBeenCalled();
  expect(screen.getByRole("checkbox")).toHaveAttribute("aria-invalid", "true");
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(
    screen.getByRole("button", { name: "Подтвердить выпуск" }),
  );
  await screen.findByText(
    "Ответ не получен. Проверьте историю или повторите отправку без изменения данных.",
  );
  expect(screen.getByLabelText("Фактический расход")).toHaveValue("0,75");
  await userEvent.click(
    screen.getByRole("button", { name: "Подтвердить выпуск" }),
  );
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(produce.mock.calls[0]?.[1]).toBe(produce.mock.calls[1]?.[1]);
  expect(produce.mock.calls[0]?.[0]).toEqual(
    expect.objectContaining({
      recipe_id: "recipe",
      actual_yield: 10,
      consumption: [{ batch_id: "batch", quantity: "0.75", unit: "kg" }],
    }),
  );
});
