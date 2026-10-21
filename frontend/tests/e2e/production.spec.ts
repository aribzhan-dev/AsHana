import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";

test.use({ trace: "off", screenshot: "off", video: "off" });
test("кухня: версия рецепта, фактический выпуск и история в обеих темах", async ({
  page,
}, testInfo) => {
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/staff/production");
  await page.getByLabel("Логин", { exact: true }).fill("cook.ui");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Производство", exact: true }),
  ).toBeVisible();
  const original = page.locator(".production-card").filter({
    has: page.getByRole("heading", { name: "Каша для кухни", exact: true }),
  });
  await original
    .getByRole("button", { name: "Новая версия", exact: true })
    .click();
  let dialog = page.getByRole("dialog", { name: "Новая версия", exact: true });
  await dialog.getByLabel("Плановый выход").fill("15");
  await dialog.getByLabel("Норма на весь плановый выпуск").fill("1500,125");
  await dialog
    .getByLabel("Технология приготовления")
    .fill("Обновлённая технологическая карта");
  await dialog.getByRole("button", { name: "Сохранить версию" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByText("Версия рецепта сохранена", { exact: true }),
  ).toBeVisible();
  const updated = page
    .locator(".production-card")
    .filter({
      has: page.getByRole("heading", { name: "Каша для кухни", exact: true }),
    })
    .filter({ hasText: "Версия 2" });
  await expect(updated).toContainText("1,500125");
  await updated.getByRole("button", { name: "Выпустить продукцию" }).click();
  dialog = page.getByRole("dialog", {
    name: "Выпустить продукцию",
    exact: true,
  });
  await dialog
    .getByLabel("Партия сырья 1")
    .selectOption({ label: "Рис кухня 1 · 1 кг · Доступна" });
  await dialog.getByLabel("Фактический расход", { exact: true }).fill("0,75");
  await dialog
    .getByLabel("Обозначение партии")
    .fill("Утренний выпуск из браузера");
  await dialog.getByLabel("Фактический выход", { exact: true }).fill("9");
  const expires = new Date(Date.now() + 24 * 3600000 + 5 * 3600000)
    .toISOString()
    .slice(0, 16);
  await dialog.getByLabel("Годна до (Алматы)").fill(expires);
  await dialog.getByRole("checkbox").check();
  await page.setViewportSize({ width: 390, height: 900 });
  // Only synthetic stock data remains on the screen; auth recording is disabled.
  await page.screenshot({
    path: testInfo.outputPath("production-form-390.png"),
    fullPage: false,
  });
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
  await dialog.getByRole("button", { name: "Подтвердить выпуск" }).click();
  await expect(dialog).not.toBeVisible();
  const produced = page.locator(".production-card").filter({
    has: page.getByRole("heading", {
      name: "Утренний выпуск из браузера",
      exact: true,
    }),
  });
  await expect(produced).toContainText("9 порций");
  await expect(produced).toContainText("0,75 кг");
  await expect(produced).toContainText("Версия 2");
  await produced.getByRole("button", { name: "Рецепт выпуска" }).click();
  dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Обновлённая технологическая карта");
  await expect(dialog).toContainText("15 порций");
  await page.keyboard.press("Escape");
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      for (const section of ["Рецепты", "История выпусков"]) {
        await page.getByRole("button", { name: section, exact: true }).click();
        await expect(page.locator(".production-card").first()).toBeVisible();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        if (
          (width === 390 && theme === "light") ||
          (width === 1280 && theme === "dark")
        )
          await page.screenshot({
            path: testInfo.outputPath(
              `${section === "Рецепты" ? "recipes" : "production"}-${width}-${theme}.png`,
            ),
            fullPage: false,
          });
      }
      await page
        .getByRole("button", { name: "Создать рецепт", exact: true })
        .click();
      dialog = page.getByRole("dialog", {
        name: "Создать рецепт",
        exact: true,
      });
      await expect(dialog.getByLabel("Готовая продукция")).toBeVisible();
      expect(
        await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true);
      await dialog
        .getByRole("button", { name: "Закрыть", exact: true })
        .click();
    }
  }
  const stockResponse = await page.request.get("/api/v1/inventory/batches");
  expect(stockResponse.status()).toBe(403);
});
test("гость не видит рецепты и расход сырья", async ({ page }) => {
  await page.goto("/staff/production");
  await expect(
    page.getByRole("heading", { name: "Войти", exact: true }),
  ).toBeVisible();
  expect((await page.request.get("/api/v1/production/recipes")).status()).toBe(
    401,
  );
  await expect(
    page.getByRole("button", { name: "Создать рецепт" }),
  ).toHaveCount(0);
});
