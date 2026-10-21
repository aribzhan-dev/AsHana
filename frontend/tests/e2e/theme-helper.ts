import { expect, type Page } from "@playwright/test";
export async function selectTheme(page: Page, theme: string) {
  await page.getByRole("button", { name: /Тема оформления:/ }).click();
  const dialog = page.getByRole("dialog", {
    name: "Тема оформления",
    exact: true,
  });
  await expect(dialog).toBeVisible();
  const label =
    theme === "dark"
      ? "Тёмная"
      : theme === "light"
        ? "Светлая"
        : "Как на устройстве";
  await dialog.getByRole("button", { name: label, exact: true }).click();
  await expect(dialog).not.toBeVisible();
}
