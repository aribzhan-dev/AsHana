import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";
test.use({ trace: "off", screenshot: "off", video: "off" });
test("отчёты: demo отдельно, четыре вида, фильтры и адаптивность", async ({
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
  const results = page.getByRole("region", { name: "Результат отчёта" });
  await expect(results).toBeVisible();
  await expect(results).toContainText("Поступления");
  await page.getByLabel("Режим оплаты").selectOption("real");
  await page.getByRole("button", { name: "Показать отчёт" }).click();
  await expect(results).toContainText("реальных поступлений нет");
  await expect(results).toContainText("Найдено строк: 0");
  for (const kind of ["production", "stock", "writeoffs"]) {
    await page.getByLabel("Вид отчёта").selectOption(kind);
    await page.getByRole("button", { name: "Показать отчёт" }).click();
    await expect(results).toBeVisible();
    await expect(results.locator(".compact-record").first()).toBeVisible();
  }
  await page.getByLabel("Вид отчёта").selectOption("stock");
  await page.getByRole("button", { name: "Показать отчёт" }).click();
  await expect(results).toContainText("не исторический");
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
  await expect(results).toBeVisible();
});
