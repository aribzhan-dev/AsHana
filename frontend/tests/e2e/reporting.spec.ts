import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";
test.use({ trace: "off", screenshot: "off", video: "off" });
test("отчёты: меню видов, сводка, таблицы и адаптивность", async ({
  page,
}, testInfo) => {
  test.setTimeout(120000);
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/staff/reports");
  await page.getByLabel("Логин", { exact: true }).fill("catalog.manager");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  const nav = page.getByRole("navigation", { name: "Виды отчётов" });
  await expect(page.locator(".kpi-grid")).toContainText("Выручка");
  await expect(page.locator(".hour-chart")).toBeVisible();
  for (const name of [
    "Продажи",
    "ТОП товаров",
    "ABC-анализ",
    "Не продавались",
    "Возвраты",
    "Инвентаризация",
    "Списания",
    "Производство",
    "Расходы и закупки",
    "Кассовая книга",
  ]) {
    await nav.getByRole("button", { name, exact: true }).click();
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
    await expect(
      page.locator(".report-table, .empty-state").first(),
    ).toBeVisible();
  }
  for (const name of ["Остатки сейчас", "Долги поставщикам"]) {
    await nav.getByRole("button", { name, exact: true }).click();
    await expect(page.getByLabel("С даты (Астана)")).toHaveCount(0);
    await expect(
      page.locator(".report-table, .empty-state").first(),
    ).toBeVisible();
  }
  await nav.getByRole("button", { name: "Продажи", exact: true }).click();
  await page.getByRole("button", { name: "30 дней", exact: true }).click();
  await expect(page.locator(".report-table").first()).toBeVisible();
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (width === 390)
        await page.screenshot({
          path: testInfo.outputPath(`reports-${theme}.png`),
        });
    }
  }
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Продажи", exact: true }),
  ).toBeVisible();
});
