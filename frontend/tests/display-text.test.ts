import { expect, it } from "vitest";
import { displayText } from "../src/shared/lib/display-text";
it("начальные подписи меняются только для известных записей, обычный текст сохраняется", () => {
  expect(displayText("Демо-поставка")).toBe("Начальная поставка");
  expect(displayText("Поставка от пекарни")).toBe("Поставка от пекарни");
  expect(
    displayText(
      "Демонстрационный рецепт: не утверждённая технологическая карта.",
    ),
  ).toBe("Технологию приготовления необходимо заполнить.");
});
