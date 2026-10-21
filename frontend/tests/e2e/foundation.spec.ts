import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";

test("API доступен через общий origin, клавиатура и сохранение темы", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await request.get("/api/v1/health/ready");
  expect(response.ok()).toBe(true);
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText("Меню обновлено:");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Перейти к содержимому" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  await selectTheme(page, "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(
    page.getByRole("button", { name: "Тема оформления: Тёмная" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("тема устройства меняется без перезагрузки", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Тема оформления: Как на устройстве" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Меню обновлено:");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("ошибка подключения и повтор", async ({ page }) => {
  await page.route("**/api/v1/catalog/menu?**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: "{}",
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText(
    "Не удалось выполнить действие",
  );
  await page.unroute("**/api/v1/catalog/menu?**");
  await page.getByRole("button", { name: "Обновить меню" }).click();
  await expect(page.getByRole("status")).toContainText("Меню обновлено:");
});

for (const width of [360, 390, 768, 1280, 1440]) {
  for (const theme of ["light", "dark"]) {
    test(`экран ${width}, тема ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await selectTheme(page, theme);
      await expect(page.getByRole("status")).toContainText("Меню обновлено:");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const retry = page.getByRole("button", { name: "Обновить меню" });
      await retry.scrollIntoViewIfNeeded();
      await expect(retry).toBeInViewport();
      const buttonBox = await retry.boundingBox();
      expect(buttonBox?.height).toBeGreaterThanOrEqual(44);
      await retry.click();
      await expect(page.getByRole("status")).toContainText("Меню обновлено:");
      await page.screenshot({
        path: testInfo.outputPath(`${theme}-${width}.png`),
        fullPage: true,
      });
    });
  }
}
