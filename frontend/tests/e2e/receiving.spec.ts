import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";
test.use({ trace: "off", screenshot: "off", video: "off" });
test("накладная: товар внутри формы, штрихкод, расходы, склад и компактные детали", async ({
  page,
}, testInfo) => {
  test.setTimeout(120000);
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/staff/receipts");
  await page.getByLabel("Логин", { exact: true }).fill("stock.other");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await page.getByRole("button", { name: "Новая накладная" }).click();
  await page.getByLabel("Номер накладной").fill("UI-накладная-01");
  for (const [field, name] of [
    ["Поставщик", "Поставщик UI"],
    ["Склад", "Склад UI"],
    ["Способ оплаты", "Перевод UI"],
  ]) {
    await page
      .getByLabel(field!, { exact: true })
      .locator("../..")
      .getByRole("button", { name: "Добавить", exact: true })
      .click();
    const d = page.getByRole("dialog");
    await d.getByLabel("Название", { exact: true }).fill(name!);
    await d.getByRole("button", { name: "Создать", exact: true }).click();
    await expect(d).not.toBeVisible();
  }
  await page
    .getByRole("button", { name: "Создать товар", exact: true })
    .click();
  let dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Название", { exact: true })
    .fill("Напиток со штрихкодом UI");
  await dialog.getByLabel("Тип позиции").selectOption("purchased");
  await dialog.getByLabel("Штрихкод", { exact: true }).fill("4870000000018");
  await dialog.getByLabel("Категория", { exact: true }).fill("Вода");
  await dialog.getByLabel("Закупочная цена, ₸", { exact: true }).fill("100,50");
  await dialog.getByLabel("Цена продажи, ₸", { exact: true }).fill("200");
  await dialog.getByRole("button", { name: "Создать товар" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByLabel("Товар 1", { exact: true })).not.toHaveValue("");
  await expect(page.getByLabel("Цена за единицу, ₸")).toHaveValue("100.5");
  await page.getByLabel("Количество, шт").fill("3");
  await page.getByLabel("Цена за единицу, ₸").fill("100,50");
  await page
    .getByLabel("Годен до (Астана)")
    .fill(
      new Date(Date.now() + 86400000 + 5 * 3600000).toISOString().slice(0, 16),
    );
  await page.getByLabel("Дополнительные расходы, ₸").fill("20");
  await expect(page.locator(".invoice-totals")).toContainText("321,50");
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 950 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (width !== 768)
        await page.screenshot({
          path: testInfo.outputPath(`invoice-${width}-${theme}.png`),
          fullPage: true,
          animations: "disabled",
        });
    }
  }
  await page.getByRole("button", { name: "Провести приход" }).click();
  await expect(
    page.getByRole("button", { name: "Новая накладная" }),
  ).toBeVisible();
  const row = page
    .locator(".compact-record")
    .filter({ hasText: "UI-накладная-01" });
  await expect(row).toContainText("321,50");
  await row.getByRole("button", { name: /Подробнее/ }).click();
  dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Напиток со штрихкодом UI");
  await expect(dialog).toContainText("Расходы: 20,00");
  await page.keyboard.press("Escape");
  await page.goto("/staff/inventory");
  await page
    .getByRole("combobox", { name: "Склад", exact: true })
    .selectOption({ label: "Склад UI" });
  await expect(page.locator(".stock-batch")).toHaveCount(1);
  await expect(page.locator(".stock-batch")).toContainText(
    "Напиток со штрихкодом UI",
  );
  await page.goto("/staff/settings");
  await expect(
    page.getByRole("heading", { name: "Настройки", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".stock-items")).toContainText("Перевод UI");
  await page.goto("/staff/products");
  await expect(page.getByRole("form", { name: "Создать товар" })).toHaveCount(
    0,
  );
  await page.getByLabel("Найти товар").fill("Напиток со штрихкодом UI");
  const product = page
    .locator(".stock-items li")
    .filter({ hasText: "Напиток со штрихкодом UI" });
  await product
    .getByRole("button", { name: "Редактировать", exact: true })
    .click();
  dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Категория", { exact: true })).toHaveValue(
    "Вода",
  );
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 950 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: testInfo.outputPath(`product-editor-${width}.png`),
      animations: "disabled",
    });
  }
  await dialog.getByLabel("Цена продажи, ₸", { exact: true }).fill("250");
  await dialog.getByRole("button", { name: "Сохранить изменения" }).click();
  await expect(dialog).not.toBeVisible();
  await product.getByRole("button", { name: /Подробнее/ }).click();
  await expect(page.getByRole("dialog")).toContainText("250,00");
  await page.keyboard.press("Escape");
  for (const width of [360, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    if (width < 768) {
      const menu = page.getByRole("button", { name: "Меню", exact: true });
      await menu.click();
      const drawer = page.getByRole("dialog", { name: "Меню", exact: true });
      await expect(drawer).toBeVisible();
      await expect(
        drawer.getByRole("link", { name: "Поступления", exact: true }),
      ).toBeVisible();
      await expect.poll(async () => (await drawer.boundingBox())?.x).toBe(0);
      await page.screenshot({
        path: testInfo.outputPath(`drawer-${width}.png`),
        animations: "disabled",
      });
      await page.keyboard.press("Escape");
      await expect(menu).toBeFocused();
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});
