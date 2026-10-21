import { expect, test } from "@playwright/test";
import { selectTheme } from "./theme-helper";

test.use({ trace: "off", screenshot: "off", video: "off" });
test("склад: приход, списание, пересчёт, история и мобильные темы", async ({
  page,
}, testInfo) => {
  test.skip(!process.env.ASHANA_TEST_PASSWORD, "Нужен изолированный стенд");
  await page.goto("/staff/inventory");
  await page.getByLabel("Логин", { exact: true }).fill("stock.other");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.ASHANA_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Склад", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Позиции склада", exact: true })
    .click();
  const itemForm = page.getByRole("form", { name: "Добавить позицию" });
  await itemForm
    .getByLabel("Название", { exact: true })
    .fill("Рис для браузерной проверки");
  await itemForm.getByRole("button", { name: "Добавить позицию" }).click();
  await expect(
    page.getByText("Позиция добавлена", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Приход", exact: true }).click();
  const receipt = page.getByRole("form", { name: "Оформить приход" });
  await receipt
    .getByLabel("Позиция", { exact: true })
    .selectOption({ label: "Рис для браузерной проверки · кг" });
  await receipt.getByLabel("Обозначение партии").fill("Браузерная партия");
  await receipt.getByLabel("Количество", { exact: true }).fill("1250,125");
  await receipt.getByLabel("Единица", { exact: true }).selectOption("g");
  await receipt
    .getByLabel("Общая закупочная стоимость, ₸", { exact: true })
    .fill("123,45");
  await receipt
    .getByLabel("Источник / поставщик", { exact: true })
    .fill("Тестовая накладная");
  const expires = new Date(Date.now() + 3 * 24 * 3600000 + 5 * 3600000)
    .toISOString()
    .slice(0, 16);
  await receipt.getByLabel("Годна до (Алматы)", { exact: true }).fill(expires);
  await receipt.getByRole("button", { name: "Оформить приход" }).click();
  await expect(
    page.getByText("Приход сохранён", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Партии и остатки", exact: true })
    .click();
  const batch = page.locator(".stock-batch").filter({
    has: page.getByRole("heading", {
      name: "Рис для браузерной проверки",
      exact: true,
    }),
  });
  await expect(batch).toContainText("1,250125");
  await batch.getByRole("button", { name: "Списать", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "Списание", exact: true });
  await dialog.getByLabel("Количество", { exact: true }).fill("0,25");
  await dialog
    .getByLabel("Причина", { exact: true })
    .fill("Повреждена упаковка");
  await dialog.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(batch).toContainText("1,000125");
  await batch.getByRole("button", { name: "Пересчитать", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Инвентаризация", exact: true });
  await dialog
    .getByLabel("Фактический остаток", { exact: true })
    .fill("1000,125");
  await dialog.getByLabel("Единица", { exact: true }).selectOption("g");
  await dialog
    .getByLabel("Причина", { exact: true })
    .fill("Контрольное взвешивание");
  await dialog.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(dialog).not.toBeVisible();
  await batch
    .getByRole("button", { name: "Приостановить", exact: true })
    .click();
  dialog = page.getByRole("dialog", { name: "Приостановка", exact: true });
  await dialog
    .getByLabel("Причина", { exact: true })
    .fill("Проверка маркировки");
  await dialog.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(
    batch.getByText("Приостановлена", { exact: true }),
  ).toBeVisible();
  const available = batch
    .locator(".stock-balances > div")
    .filter({ has: page.getByText("Доступно сейчас", { exact: true }) });
  await expect(available.locator("dd")).toHaveText("0 кг");
  await batch.getByRole("button", { name: "Возобновить", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Возобновление", exact: true });
  await dialog
    .getByLabel("Причина", { exact: true })
    .fill("Маркировка проверена");
  await dialog.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(available.locator("dd")).toHaveText("1,000125 кг");
  await batch
    .getByRole("button", { name: "История движений", exact: true })
    .click();
  dialog = page.getByRole("dialog", { name: "История движений", exact: true });
  await expect(
    dialog.getByText("Повреждена упаковка", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByText("Контрольное взвешивание", { exact: true }),
  ).toBeVisible();
  await expect(dialog.locator("li")).toHaveCount(5);
  await dialog.getByRole("button", { name: "Закрыть", exact: true }).click();
  for (const width of [360, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["light", "dark"]) {
      await selectTheme(page, theme);
      for (const section of ["Партии и остатки", "Приход", "Позиции склада"]) {
        await page.getByRole("button", { name: section, exact: true }).click();
        if (
          section === "Приход" &&
          ((width === 390 && theme === "light") ||
            (width === 1280 && theme === "dark"))
        )
          await page.screenshot({
            path: testInfo.outputPath(`receipt-${width}-${theme}.png`),
            fullPage: true,
          });
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
      }
      await page
        .getByRole("button", { name: "Партии и остатки", exact: true })
        .click();
      if (
        (width === 390 && theme === "light") ||
        (width === 1280 && theme === "dark")
      )
        await page.screenshot({
          path: testInfo.outputPath(`inventory-${width}-${theme}.png`),
          fullPage: true,
        });
    }
  }
});

test("страница склада предлагает вход без раскрытия остатков", async ({
  page,
}) => {
  await page.goto("/staff/inventory");
  await expect(
    page.getByRole("heading", { name: "Войти", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Физический остаток", { exact: true }),
  ).toHaveCount(0);
});
