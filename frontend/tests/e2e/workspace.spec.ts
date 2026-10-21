import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";
test.use({ trace: "off", screenshot: "off", video: "off" });
test("рабочий кабинет: обзор, навигация, профиль и управляемые роли", async ({
  page,
}, testInfo) => {
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/staff");
  await page.getByLabel("Логин", { exact: true }).fill("stock.admin");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Обзор столовой" }),
  ).toBeVisible();
  const csrf = (await (await page.request.get("/api/v1/auth/csrf")).json()) as {
    csrf_token: string;
  };
  const created = await page.request.post("/api/v1/admin/users", {
    headers: {
      "x-csrf-token": csrf.csrf_token,
      origin: new URL(page.url()).origin,
    },
    data: {
      login: "workspace.browser",
      name: "Руководитель",
      password: process.env.ASHANA_TEST_PASSWORD!,
      roles: ["admin", "manager"],
    },
  });
  expect(created.status()).toBe(201);
  await page.goto("/staff/profile");
  await page.getByRole("button", { name: "Выйти", exact: true }).click();
  await page.getByLabel("Логин", { exact: true }).fill("workspace.browser");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Руководитель", exact: true }),
  ).toBeVisible();
  await page.goto("/staff");
  await expect(
    page.getByRole("heading", { name: "Лидеры продаж" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ваши сессии" })).toHaveCount(
    0,
  );
  await expect(page.locator("main")).not.toContainText("ДЕМО");
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (width === 1440 || width === 390)
        await page.screenshot({
          path: testInfo.outputPath(`workspace-${width}-${theme}.png`),
          fullPage: true,
        });
    }
  }
  await page
    .getByRole("navigation", { name: "Разделы управления" })
    .getByRole("link", { name: "Сотрудники и роли" })
    .click();
  await page
    .getByRole("button", { name: "Роли и доступ", exact: true })
    .click();
  await page.getByRole("button", { name: "Создать роль" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Название роли").fill("Наблюдатель заказов");
  await dialog.getByLabel("Код роли").fill("observer_browser");
  await dialog.getByLabel("Заказы: просмотр входящих", { exact: true }).check();
  await dialog.getByRole("button", { name: "Сохранить роль" }).click();
  await expect(dialog).toHaveCount(0);
  const role = page.locator(".role-cards .card").filter({
    has: page.getByRole("heading", { name: "Наблюдатель заказов" }),
  });
  await role.getByRole("button", { name: "Изменить" }).click();
  await dialog.getByLabel("Название роли").fill("Контроль заказов");
  await dialog.getByRole("button", { name: "Сохранить роль" }).click();
  await expect(
    page.getByRole("heading", { name: "Контроль заказов" }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Разделы управления" })
    .getByRole("link", { name: "Мой профиль" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Ваши сессии" }),
  ).toBeVisible();
});
