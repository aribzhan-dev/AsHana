import { expect, test } from "@playwright/test";
import { selectTheme, tabKey } from "./theme-helper";
import type { Page } from "@playwright/test";

const menuReady = (page: Page) =>
  expect(
    page.locator('.food-grid, .empty-state:not([role="status"])').first(),
  ).toBeVisible();

test("API доступен через общий origin, клавиатура и сохранение темы", async ({
  page,
  request,
  browserName,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await request.get("/api/v1/health/ready");
  expect(response.ok()).toBe(true);
  await page.goto("/");
  await menuReady(page);
  await page.keyboard.press(tabKey(browserName));
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
  await menuReady(page);
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
  await page.getByRole("button", { name: "Повторить" }).click();
  await menuReady(page);
});

for (const width of [360, 390, 768, 1280, 1440]) {
  for (const theme of ["light", "dark"]) {
    test(`экран ${width}, тема ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await selectTheme(page, theme);
      await menuReady(page);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      // Phones use the bottom tab bar; wide screens show the same link in the header.
      const tab =
        width < 900
          ? page
              .getByRole("navigation", { name: "Разделы для гостя" })
              .getByRole("link", { name: "Заказы" })
          : page.getByRole("link", { name: "Мои заказы" });
      await expect(tab).toBeInViewport();
      const tabBox = await tab.boundingBox();
      if (width < 900) expect(tabBox?.height).toBeGreaterThanOrEqual(44);
      await page.screenshot({
        path: testInfo.outputPath(`${theme}-${width}.png`),
        fullPage: true,
      });
    });
  }
}
