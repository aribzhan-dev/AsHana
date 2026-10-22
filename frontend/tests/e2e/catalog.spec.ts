import { expect, test, type Page, type Locator } from "@playwright/test";
import { selectTheme } from "./theme-helper";
async function findCard(page: Page, card: Locator) {
  for (let n = 0; n < 10; n++) {
    await expect(page.locator(".stock-pagination")).toBeVisible();
    if (await card.count()) return;
    const next = page.getByRole("button", {
      name: /^(Далее|Следующая страница)$/,
    });
    await expect(next).toBeEnabled();
    const response = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v1/catalog/") && r.request().method() === "GET",
    );
    await next.click();
    await response;
  }
  await expect(card).toBeVisible();
}
test.use({ trace: "off", screenshot: "off", video: "off" });
test("меню: черновик, публикация готового остатка, цена и снятие в обеих темах", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120000);
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/staff/catalog");
  await page.getByLabel("Логин", { exact: true }).fill("catalog.manager");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Меню и периоды", exact: true }),
  ).toBeVisible();
  const starts = new Date(Date.now() + 5 * 3600000).toISOString().slice(0, 16),
    ends = new Date(Date.now() + 6 * 3600000).toISOString().slice(0, 16);
  await page
    .getByRole("button", { name: "Добавить период", exact: true })
    .click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("Название периода").fill("Обед из браузера");
  await dialog.getByLabel("Начало (Астана)").fill(starts);
  await dialog.getByLabel("Окончание (Астана)").fill(ends);
  await expect(dialog.getByLabel("Опубликовать период")).not.toBeChecked();
  await dialog.getByRole("button", { name: "Сохранить период" }).click();
  await expect(dialog).not.toBeVisible();
  const period = page.locator(".production-card").filter({
    has: page.getByRole("heading", { name: "Обед из браузера", exact: true }),
  });
  await findCard(page, period);
  await expect(period).toContainText("Не опубликовано");
  await findCard(page, period);
  await period.getByRole("button", { name: "Настроить меню" }).click();
  await page
    .getByRole("button", { name: "Добавить в меню", exact: true })
    .click();
  dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Тип продукции")).toBeEnabled();
  await expect(
    dialog.getByLabel("Тип продукции").locator("option"),
  ).toHaveCount(2);
  await dialog.getByLabel("Тип продукции").selectOption("purchased");
  await expect(dialog.getByLabel("Готовая продукция")).toBeEnabled();
  await dialog
    .getByLabel("Готовая продукция")
    .selectOption({ label: "Сок для меню браузера" });
  await dialog.getByLabel("Порция / упаковка").fill("Бутылка 0,5 л");
  await dialog.getByLabel("Описание", { exact: true }).fill("Яблочный сок");
  await dialog.getByLabel("Цена, ₸").fill("123,45");
  await dialog.getByLabel("Опубликовать позицию").check();
  await page.setViewportSize({ width: 390, height: 900 });
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
  await page.screenshot({ path: testInfo.outputPath("catalog-entry-390.png") });
  await dialog.getByRole("button", { name: "Сохранить позицию" }).click();
  await expect(dialog).not.toBeVisible();
  const guest = await browser.newContext({
    baseURL: testInfo.project.use.baseURL,
  });
  const menu = await guest.newPage();
  await menu.goto("/");
  await expect(
    menu.locator('.food-grid, .empty-state:not([role="status"])').first(),
  ).toBeVisible();
  await expect(
    menu.getByRole("heading", { name: "Сок для меню браузера", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "К периодам", exact: true }).click();
  await findCard(page, period);
  await period.getByRole("button", { name: "Изменить период" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Опубликовать период").check();
  await dialog.getByRole("button", { name: "Сохранить период" }).click();
  await expect(dialog).not.toBeVisible();
  await menu.reload();
  const publicCard = menu.locator(".food-card").filter({
    has: menu.getByRole("heading", {
      name: "Сок для меню браузера",
      exact: true,
    }),
  });
  await findCard(menu, publicCard);
  await expect(publicCard).toContainText("123,45");
  await expect(publicCard).toContainText("Бутылка 0,5 л");
  await expect(
    publicCard.getByRole("button", {
      name: "Добавить в корзину: Сок для меню браузера",
    }),
  ).toBeVisible();
  await publicCard
    .getByRole("button", { name: "Подробнее: Сок для меню браузера" })
    .click();
  await expect(menu.getByRole("dialog")).toContainText("8 шт");
  await menu
    .getByRole("dialog")
    .getByRole("button", { name: "Закрыть", exact: true })
    .click();
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await menu.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      await selectTheme(menu, theme);
      for (const target of [page, menu])
        expect(
          await target.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
      await findCard(page, period);
      await period.getByRole("button", { name: "Изменить период" }).click();
      dialog = page.getByRole("dialog");
      expect(
        await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth),
      ).toBe(true);
      await dialog
        .getByRole("button", { name: "Закрыть", exact: true })
        .click();
      if (
        (width === 390 && theme === "light") ||
        (width === 1280 && theme === "dark")
      )
        await menu.screenshot({
          path: testInfo.outputPath(`menu-${width}-${theme}.png`),
          fullPage: true,
        });
    }
  }
  await findCard(page, period);
  await period.getByRole("button", { name: "Настроить меню" }).click();
  const entry = page.locator(".production-card").filter({
    has: page.getByRole("heading", {
      name: "Сок для меню браузера",
      exact: true,
    }),
  });
  await entry.getByRole("button", { name: "Изменить позицию" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Цена, ₸").fill("150,99");
  await dialog.getByRole("button", { name: "Сохранить позицию" }).click();
  await expect(dialog).not.toBeVisible();
  await menu.reload();
  await findCard(menu, publicCard);
  await expect(publicCard).toContainText("150,99");
  await entry.getByRole("button", { name: "Изменить позицию" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Опубликовать позицию").uncheck();
  await dialog.getByRole("button", { name: "Сохранить позицию" }).click();
  await expect(dialog).not.toBeVisible();
  await menu.reload();
  await expect(
    menu.locator('.food-grid, .empty-state:not([role="status"])').first(),
  ).toBeVisible();
  await expect(publicCard).toHaveCount(0);
  expect(
    (
      await menu.request.get(
        `/api/v1/catalog/periods?day=${starts.slice(0, 10)}`,
      )
    ).status(),
  ).toBe(401);
  expect(errors).toEqual([]);
  await guest.close();
});
