import { expect, test, type Page, type Locator } from "@playwright/test";
import { selectTheme } from "./theme-helper";
import { orderDish, payWithTestCard } from "./guest-helper";
import { orderNumber } from "../../src/shared/lib/pickup-qr";
test.use({ trace: "off", screenshot: "off", video: "off" });
async function findCard(page: Page, card: Locator) {
  for (let n = 0; n < 10; n++) {
    await expect(page.locator(".stock-pagination").first()).toBeVisible();
    if (await card.count()) return;
    const response = page.waitForResponse(
      (r) => r.request().method() === "GET" && r.url().includes("/api/v1/"),
    );
    await page
      .getByRole("button", { name: "Следующая страница", exact: true })
      .first()
      .click();
    await response;
  }
  await expect(card).toBeVisible();
}
test("готовую еду комплектуют и выдают по коду один раз", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120000);
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/");
  await orderDish(page, "Обед для заказа из браузера");
  await payWithTestCard(page);
  await expect(page.getByTestId("pickup-code")).toBeVisible();
  const code = await page.getByTestId("pickup-code").innerText();
  const orders = (await (await page.request.get("/api/v1/orders")).json()) as {
    id: string;
  }[];
  const id = orders[0]!.id;
  const context = await browser.newContext({
    baseURL: testInfo.project.use.baseURL,
  });
  const staff = await context.newPage();
  await staff.goto("/staff/orders");
  await staff.getByLabel("Логин", { exact: true }).fill("catalog.manager");
  await staff
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await staff.getByRole("button", { name: "Войти", exact: true }).click();
  const card = staff.locator(".order-card").filter({
    has: staff.getByRole("heading", {
      name: `Заказ №${orderNumber(id)}`,
      exact: true,
    }),
  });
  await findCard(staff, card);
  await expect(card.getByText(code, { exact: true })).toHaveCount(0);
  await card.getByRole("button", { name: "Начать комплектацию" }).click();
  await expect(card).toContainText("Комплектуется");
  await page.getByRole("button", { name: "Обновить заказы" }).click();
  await expect(page.locator(".order-card")).toContainText("Комплектуется");
  await expect(
    page.getByRole("button", { name: "Отменить заказ", exact: true }),
  ).toHaveCount(0);
  await card
    .getByRole("button", { name: "Готов к выдаче", exact: true })
    .click();
  await expect(
    card.getByRole("button", { name: "Выдать заказ" }),
  ).toBeVisible();
  for (const width of [360, 390, 768, 1280, 1440]) {
    await staff.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(staff, theme);
      await card.getByRole("button", { name: "Выдать заказ" }).click();
      const dialog = staff.getByRole("dialog");
      expect(
        await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true);
      expect(
        await staff.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (width === 390)
        await staff.screenshot({
          path: testInfo.outputPath(`serving-${theme}.png`),
        });
      await dialog
        .getByRole("button", { name: "Закрыть", exact: true })
        .click();
    }
  }
  await card.getByRole("button", { name: "Выдать заказ" }).click();
  await staff.getByLabel("Код получения").fill("ZZZZZZZZ");
  await staff.getByRole("button", { name: "Подтвердить выдачу" }).click();
  await expect(
    staff.getByText("Введите 8 символов кода с экрана посетителя"),
  ).toBeVisible();
  await staff.getByLabel("Код получения").fill(code);
  await staff.getByRole("button", { name: "Подтвердить выдачу" }).click();
  await expect(staff.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Обновить заказы" }).click();
  await expect(page.locator(".order-card")).toContainText("Выдан");
  await expect(page.getByTestId("pickup-code")).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".order-card")).toContainText("Выдан");
  await context.close();
});

test("стойка выдаёт заказ по QR-коду гостя", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120000);
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/");
  await orderDish(page, "Обед для заказа из браузера");
  await payWithTestCard(page);
  await expect(
    page.getByRole("img", { name: /QR-код заказа №/ }),
  ).toBeVisible();
  const [order] = (await (await page.request.get("/api/v1/orders")).json()) as {
    id: string;
    pickup_code: string;
  }[];
  const context = await browser.newContext({
    baseURL: testInfo.project.use.baseURL,
  });
  const staff = await context.newPage();
  await staff.goto("/staff/orders");
  await staff.getByLabel("Логин", { exact: true }).fill("catalog.manager");
  await staff
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await staff.getByRole("button", { name: "Войти", exact: true }).click();
  const card = staff.locator(".order-card").filter({
    has: staff.getByRole("heading", {
      name: `Заказ №${orderNumber(order!.id)}`,
      exact: true,
    }),
  });
  await findCard(staff, card);
  await card.getByRole("button", { name: "Начать комплектацию" }).click();
  await card
    .getByRole("button", { name: "Готов к выдаче", exact: true })
    .click();
  await expect(
    card.getByRole("button", { name: "Выдать заказ" }),
  ).toBeVisible();
  await staff.goto("/staff/scan");
  const field = staff.getByLabel("Ручной сканер или вставка данных");
  await field.fill(`ASHANA1:${order!.id}:${order!.pickup_code}`);
  await field.press("Enter");
  await staff.getByRole("button", { name: "Выдать заказ" }).click();
  await expect(staff.getByText(/выдан$/)).toBeVisible();
  await page.reload();
  await expect(page.locator(".order-card").first()).toContainText("Выдан");
  await context.close();
});

test("кухня видит оплаченный заказ сразу, без обновления страницы", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120000);
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  const context = await browser.newContext({
    baseURL: testInfo.project.use.baseURL,
  });
  const staff = await context.newPage();
  await staff.goto("/admin/orders");
  await staff.getByLabel("Логин", { exact: true }).fill("catalog.manager");
  await staff
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await staff.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(staff.getByText("Обновляется сразу")).toBeVisible({
    timeout: 15000,
  });
  await page.goto("/");
  await orderDish(page, "Обед для заказа из браузера");
  await payWithTestCard(page);
  await expect(
    page.getByRole("img", { name: /QR-код заказа №/ }),
  ).toBeVisible();
  const [order] = (await (await page.request.get("/api/v1/orders")).json()) as {
    id: string;
  }[];
  const number = orderNumber(order!.id);
  // Polling is 60 s while connected, so seeing it within 5 s proves the live channel.
  await expect(staff.getByRole("alert")).toContainText(
    `Новый заказ №${number}`,
    { timeout: 5000 },
  );
  await context.close();
});
