import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";
test.use({ trace: "off", screenshot: "off", video: "off" });

test("финансы: сотрудник с оплатой за день, смена, выплата и итоги месяца", async ({
  page,
}) => {
  test.setTimeout(120000);
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/admin/finance#payroll");
  await page.getByLabel("Логин", { exact: true }).fill("finance.manager");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Финансы" })).toBeVisible();
  const name = `Мойщица ${Date.now()}`;
  await page.getByRole("button", { name: "Добавить сотрудника" }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("Имя", { exact: true }).fill(name);
  await dialog.getByLabel("За рабочий день, ₸").fill("5000");
  await dialog.getByRole("button", { name: "Сохранить" }).click();
  await expect(dialog).toHaveCount(0);
  // The payments list below repeats the name; the accrual is in the payroll table.
  const row = page.locator(".payroll-table tr").filter({ hasText: name });
  await expect(row).toContainText("5 000 ₸ в день");

  await page.getByRole("tab", { name: "Табель" }).click();
  await page.getByRole("button", { name: "Добавить смену" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Сотрудник").selectOption({ label: name });
  const today = new Date(Date.now() + 5 * 3600000).toISOString().slice(0, 10);
  await dialog.getByLabel("Начало (Астана)").fill(`${today}T00:10`);
  await dialog.getByLabel("Конец (Астана)").fill(`${today}T00:40`);
  await dialog.getByRole("button", { name: "Добавить" }).click();
  await expect(dialog).toHaveCount(0);

  await page.getByRole("tab", { name: "Зарплата" }).click();
  await expect(row).toContainText("5 000 ₸");
  await row.getByRole("button", { name: "Выплатить" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Сумма, ₸").fill("2000");
  await dialog.getByRole("button", { name: "Выплатить" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(row).toContainText("3 000 ₸");

  await page.getByRole("tab", { name: "Итоги месяца" }).click();
  await expect(page.getByText("Чистая прибыль").first()).toBeVisible();
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
});
