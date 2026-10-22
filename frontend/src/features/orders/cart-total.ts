import type { PublicEntry } from "../../shared/api/catalog";

export type CartLine = { entry: PublicEntry; quantity: number };

export function cartTotal(lines: CartLine[]) {
  return lines.reduce((sum, l) => sum + l.quantity * l.entry.price_minor, 0);
}

// Takeaway cutlery is ordinary stocked goods in this category, chosen only in the cart.
export const CUTLERY_CATEGORY = "Приборы";
export const isCutlery = (entry: PublicEntry) =>
  entry.category.trim().toLocaleLowerCase("ru") ===
  CUTLERY_CATEGORY.toLocaleLowerCase("ru");
