import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";
test.use({ trace: "off", screenshot: "off", video: "off" });
test("оплата предшествует заказу; гость, кухня, отмена и мобильные темы", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120000);
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/");
  const card = page.locator(".catalog-card").filter({
    has: page.getByRole("heading", {
      name: "Обед для заказа из браузера",
      exact: true,
    }),
  });
  for (let n = 0; n < 10 && (await card.count()) === 0; n++) {
    await expect(
      page.getByRole("status").filter({ hasText: "Меню обновлено:" }),
    ).toBeVisible();
    if (await card.count()) break;
    await page.getByRole("button", { name: "Далее", exact: true }).click();
  }
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "В корзину" }).click();
  const slot = page.getByLabel("Время получения (Астана)");
  await expect(slot).toBeEnabled();
  await expect(slot.locator("option")).toHaveCount(2);
  await slot.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Заказать" }).click();
  await expect(page).toHaveURL(/\/orders$/);
  const draft = page
    .locator(".order-card")
    .filter({ hasText: "Обед для заказа из браузера" });
  await expect(draft).toContainText("Это ещё не заказ");
  expect(await (await page.request.get("/api/v1/orders")).json()).toEqual([]);
  const pending = (await (
    await page.request.get("/api/v1/orders/checkouts")
  ).json()) as { id: string }[];
  const orderId = pending[0]!.id;
  const staffContext = await browser.newContext({
    baseURL: testInfo.project.use.baseURL,
  });
  const staff = await staffContext.newPage();
  await staff.goto("/staff/orders");
  await staff.getByLabel("Логин", { exact: true }).fill("catalog.manager");
  await staff
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await staff.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    staff.getByRole("heading", { name: "Входящие заказы", exact: true }),
  ).toBeVisible();
  const staffCard = staff.locator(".order-card").filter({
    has: staff.getByRole("heading", {
      name: `Заказ ${orderId.slice(0, 8)}`,
      exact: true,
    }),
  });
  await expect(staffCard).toHaveCount(0);
  await page.route(
    "**/mock-payment",
    async (route) => {
      await route.continue({ postData: JSON.stringify({ outcome: "failed" }) });
    },
    { times: 1 },
  );
  await draft.getByRole("button", { name: "Оплатить заказ" }).click();
  await expect(draft).toContainText("Оплата не подтверждена");
  expect(await (await page.request.get("/api/v1/orders")).json()).toEqual([]);
  await draft.getByRole("button", { name: "Оплатить заказ" }).click();
  await expect(draft).toContainText("Принят");
  await expect(
    draft.getByRole("button", { name: "Оплатить заказ" }),
  ).toHaveCount(0);
  await staff.getByRole("button", { name: "Обновить заказы" }).click();
  await expect(staffCard).toContainText("Принят");
  for (const width of [360, 390, 768, 1280, 1440]) {
    for (const target of [page, staff])
      await target.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      for (const target of [page, staff]) {
        await selectTheme(target, theme);
        expect(
          await target.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
      }
      if (width === 390 || width === 1280)
        await page.screenshot({
          path: testInfo.outputPath(`order-${width}-${theme}.png`),
          fullPage: true,
        });
    }
  }
  await draft
    .getByRole("button", { name: "Отменить заказ", exact: true })
    .click();
  await expect(
    page
      .locator(".order-card")
      .filter({ hasText: "Обед для заказа из браузера" })
      .last(),
  ).toContainText("Отменён");
  await staff.getByRole("button", { name: "Обновить заказы" }).click();
  await expect(staffCard).toHaveCount(0);
  const other = await browser.newContext({
    baseURL: testInfo.project.use.baseURL,
  });
  const stranger = await other.newPage();
  await stranger.goto("/orders");
  await expect(stranger.getByText("Заказов пока нет")).toBeVisible();
  await expect(stranger.getByText("Обед для заказа из браузера")).toHaveCount(
    0,
  );
  await other.close();
  await staffContext.close();
});

test("компактный фокус логина виден в обеих темах", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/staff");
  for (const theme of ["light", "dark"]) {
    await selectTheme(page, theme);
    const login = page.getByLabel("Логин", { exact: true });
    await login.focus();
    await expect(login).toBeFocused();
    expect(
      await login.evaluate((element) => {
        const style = getComputedStyle(element);
        return [style.outlineWidth, style.outlineOffset, style.outlineStyle];
      }),
    ).toEqual(["2px", "-2px", "solid"]);
    await page.screenshot({
      path: testInfo.outputPath(`login-focus-${theme}.png`),
      fullPage: true,
    });
  }
});
