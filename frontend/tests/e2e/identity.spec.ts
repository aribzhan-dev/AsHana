import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";

test.use({ trace: "off", screenshot: "off", video: "off" });

test("гость открывает сайт без регистрации; форма сотрудника в обеих темах", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/");
  await page.getByRole("link", { name: "Для сотрудников" }).click();
  await expect(
    page.getByRole("heading", { name: "Кабинет сотрудника" }),
  ).toBeVisible();
  for (const theme of ["light", "dark"]) {
    await selectTheme(page, theme);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByText("Введите логин: 3–40 символов, начните с латинской буквы"),
  ).toBeVisible();
  const password = page.getByLabel("Пароль", { exact: true });
  await password.fill("проверка поля");
  await page.getByRole("button", { name: "Показать пароль" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Скрыть пароль" }).click();
  await expect(password).toHaveAttribute("type", "password");
  await password.fill("");
  await expect(
    page.getByText("Посетителям аккаунт не нужен", { exact: false }),
  ).toBeVisible();
});

test("администратор создаёт сотрудника, меняет роли и завершает сессию", async ({
  page,
  browser,
}, testInfo) => {
  test.skip(
    !process.env.ASHANA_TEST_PASSWORD,
    "Нужны временные данные из изолированного стенда",
  );
  const password = process.env.ASHANA_TEST_PASSWORD!;
  await page.goto("/staff");
  await page.getByLabel("Логин").fill("user01");
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Әлия", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Ваши сессии" }),
  ).toBeVisible();
  const create = page.locator(".card").filter({
    has: page.getByRole("heading", { name: "Добавить сотрудника" }),
  });
  await create.getByLabel("Имя сотрудника").fill("Нұрсұлтан");
  await create.getByLabel("Логин").fill("worker90");
  await create.getByLabel("Пароль", { exact: true }).fill(password);
  await create.getByRole("button", { name: "Добавить сотрудника" }).click();
  await expect(
    page.getByText("Сотрудник создан. Передайте ему логин и пароль лично."),
  ).toBeVisible();
  await expect(create.getByLabel("Пароль", { exact: true })).toHaveValue("");
  await expect(create.getByLabel("Телефон для связи")).toHaveAttribute(
    "placeholder",
    "+7 (7XX) XXX-XX-XX",
  );
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (
        (width === 360 && theme === "light") ||
        (width === 1280 && theme === "dark")
      ) {
        await page.screenshot({
          path: testInfo.outputPath(`staff-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    }
  }
  const workerContext = await browser.newContext({
    baseURL: process.env.ASHANA_E2E_URL,
    viewport: { width: 390, height: 844 },
  });
  try {
    const worker = await workerContext.newPage();
    await worker.goto("/staff");
    await worker.getByLabel("Логин").fill("worker90");
    await worker.getByLabel("Пароль", { exact: true }).fill(password);
    await worker.getByRole("button", { name: "Войти", exact: true }).click();
    await expect(
      worker.getByRole("heading", { name: "Нұрсұлтан", exact: true }),
    ).toBeVisible();
    await expect(
      worker.getByRole("heading", { name: "Добавить сотрудника" }),
    ).toHaveCount(0);
    const search = page
      .locator(".card")
      .filter({ has: page.getByRole("heading", { name: "Найти сотрудника" }) });
    await search.getByLabel("Логин").fill("worker90");
    await search.getByRole("button", { name: "Найти сотрудника" }).click();
    await search.getByLabel("Кухня", { exact: true }).uncheck();
    await search.getByLabel("Кассир", { exact: true }).check();
    await search.getByRole("button", { name: "Сохранить роли" }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Сохранить роли" })
      .click();
    await expect(
      page.getByText("Роли сохранены.", { exact: false }),
    ).toBeVisible();
    await worker.reload();
    await expect(
      worker.getByRole("heading", { name: "Войти", exact: true }),
    ).toBeVisible();
  } finally {
    await workerContext.close();
  }
  await page
    .getByRole("button", { name: "Завершить сессию", exact: true })
    .first()
    .click();
  const revokeDialog = page.getByRole("dialog", {
    name: "Завершить сессию?",
    exact: true,
  });
  await expect(revokeDialog).toBeVisible();
  await revokeDialog
    .getByRole("button", { name: "Отмена", exact: true })
    .click();
  await expect(revokeDialog).not.toBeVisible();
  await page.getByRole("button", { name: "Выйти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Войти", exact: true }),
  ).toBeVisible();
});

for (const width of [768, 1280, 1440]) {
  test(`форма сотрудника: ширина ${width}, клавиатура`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 });
    await page.goto("/staff");
    await expect(
      page.getByRole("heading", { name: "Войти", exact: true }),
    ).toBeVisible();
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    await page.getByLabel("Пароль", { exact: true }).focus();
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("button", { name: "Показать пароль" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Пароль", { exact: true })).toHaveAttribute(
      "type",
      "text",
    );
    await expect(
      page.getByRole("button", { name: "Скрыть пароль" }),
    ).toBeFocused();
  });
}

test("иконка темы открывает диалог: Escape, фокус и клавиатура", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/staff");
  const trigger = page.getByRole("button", { name: /Тема оформления:/ });
  await expect(trigger.locator("svg")).toBeVisible();
  const box = await trigger.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
  await trigger.click();
  const dialog = page.getByRole("dialog", {
    name: "Тема оформления",
    exact: true,
  });
  await expect(dialog).toBeVisible();
  for (let index = 0; index < 7; index++) {
    await page.keyboard.press("Tab");
    expect(
      await dialog.evaluate((element) =>
        element.contains(document.activeElement),
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await page.getByLabel("Логин", { exact: true }).focus();
  await expect(page.getByLabel("Логин", { exact: true })).toHaveAttribute(
    "placeholder",
    "Например, kassir.01",
  );
  await expect(page.getByLabel("Телефон для связи")).toHaveCount(0);
});
