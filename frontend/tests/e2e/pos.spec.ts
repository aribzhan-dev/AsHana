import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";
test.use({ trace: "off", screenshot: "off", video: "off" });
test("касса: отказ, успешная выдача, общий остаток и история после reload", async ({
  page,
}, testInfo) => {
  test.setTimeout(120000);
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/staff/pos");
  await page.getByLabel("Логин", { exact: true }).fill("catalog.manager");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  const card = page.locator(".pos-product").filter({
    has: page.getByRole("heading", {
      name: "Кассовый обед из браузера",
      exact: true,
    }),
  });
  await page.getByLabel("Поиск блюда").fill("Кассовый обед из браузера");
  await expect(card).toContainText("Свободно: 10");
  await card.getByRole("button", { name: "Добавить", exact: true }).click();
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      await page.getByRole("button", { name: "Перейти к оплате" }).click();
      const dialog = page.getByRole("dialog");
      expect(
        await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (width === 390)
        await page.screenshot({
          path: testInfo.outputPath(`pos-${theme}.png`),
        });
      await dialog
        .getByRole("button", { name: "Закрыть", exact: true })
        .click();
    }
  }
  await page.getByRole("button", { name: "Перейти к оплате" }).click();
  await page.route(
    "**/api/v1/pos/sales",
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await route.continue({
        postData: JSON.stringify({
          ...route.request().postDataJSON(),
          outcome: "failed",
        }),
      });
    },
    { times: 1 },
  );
  await page.getByRole("button", { name: "Оплата и выдача: успешно" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(card).toContainText("Свободно: 10");
  await page.getByRole("button", { name: "Перейти к оплате" }).click();
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/pos/sales") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Оплата и выдача: успешно" }).click();
  const saved = (await (await response).json()) as { id: string };
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(card).toContainText("Свободно: 9");
  await page.reload();
  await page.goto("/staff/sales");
  const receipt = page
    .locator(".compact-record")
    .filter({ hasText: saved.id.slice(0, 8) });
  await expect(receipt).toContainText("Выдано");
  await receipt.getByRole("button", { name: /Подробнее/ }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Кассовый обед из браузера",
  );
});
