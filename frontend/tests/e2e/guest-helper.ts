import { expect, type Page } from "@playwright/test";

// Adds one dish to the cart, picks the first free slot and starts checkout.
export async function orderDish(page: Page, name: string) {
  const card = page.locator(".food-card").filter({
    has: page.getByRole("heading", { name, exact: true }),
  });
  for (let n = 0; n < 10; n++) {
    // The loading spinner reuses .empty-state, so wait for the real grid.
    await expect(page.locator(".food-grid").first()).toBeVisible();
    if (await card.count()) break;
    const next = page.getByRole("button", {
      name: "Следующая страница",
      exact: true,
    });
    if (!(await next.isVisible()) || (await next.isDisabled())) break;
    const response = page.waitForResponse(
      (r) => r.url().includes("/api/v1/catalog/menu") && r.ok(),
    );
    await next.click();
    await response;
  }
  await expect(card).toBeVisible();
  await card
    .getByRole("button", { name: `Добавить в корзину: ${name}` })
    .click();
  await page.locator(".cart-bar").click();
  const sheet = page.getByRole("dialog", { name: "Ваш заказ" });
  const slots = sheet.getByRole("radio", { name: /осталось/ });
  await expect(slots).toHaveCount(1);
  await slots.first().check();
  await sheet.getByRole("button", { name: "Оформить заказ" }).click();
  await expect(page).toHaveURL(/\/orders$/);
}

// Mock checkout accepts only the published test card; fill it and pay.
export async function payWithTestCard(page: Page) {
  await page.getByRole("button", { name: "Оплатить заказ" }).click();
  const sheet = page.getByRole("dialog", { name: "Оплата картой" });
  await sheet.getByRole("button", { name: "Заполнить" }).click();
  await sheet.getByRole("button", { name: /^Оплатить \d/ }).click();
}
