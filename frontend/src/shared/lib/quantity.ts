import { uiRu as t } from "../locales/ui";

export function quantityError(
  value: string,
  min = 1,
  max = 9999,
): string | undefined {
  if (
    !/^\d+$/.test(value) ||
    !Number.isSafeInteger(Number(value)) ||
    Number(value) < min ||
    Number(value) > max
  )
    return t.quantityError;
}
