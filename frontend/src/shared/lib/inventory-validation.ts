import { inventoryRu as t } from "../locales/inventory";

export function decimalText(value: string): string {
  return value.trim().replace(",", ".");
}
export function stockQuantityError(
  value: string,
  unit: string,
  allowZero = false,
): string | undefined {
  const raw = decimalText(value);
  if (!/^[0-9]{1,12}(?:\.[0-9]{1,3})?$/.test(raw)) return t.invalidNumber;
  const number = Number(raw),
    factor = unit === "g" || unit === "ml" ? 0.001 : 1;
  if (
    number < 0 ||
    (!allowZero && number === 0) ||
    number * factor > 999999999 ||
    (["pcs", "portion"].includes(unit) && !Number.isInteger(number))
  )
    return t.invalidNumber;
}
export function costMinor(value: string): number | undefined {
  const raw = decimalText(value);
  if (!/^[0-9]{1,10}(?:\.[0-9]{1,2})?$/.test(raw)) return;
  const [whole = "0", fraction = ""] = raw.split(".");
  const minor = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return minor <= 999999999999 ? minor : undefined;
}
export function almatyInstant(value: string): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return;
  const date = new Date(`${value}+05:00`);
  if (!Number.isFinite(date.getTime())) return;
  const back = new Date(date.getTime() + 5 * 3600000)
    .toISOString()
    .slice(0, 16);
  return back === value ? date.toISOString() : undefined;
}
export function almatyNow(): string {
  return new Date(Date.now() + 5 * 3600000).toISOString().slice(0, 16);
}
export function stockDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Almaty",
  }).format(new Date(value));
}
export function stockNumber(value: string): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 6 }).format(
    Number(value),
  );
}
export function stockMoney(minor: number): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "KZT",
    currencyDisplay: "narrowSymbol",
  }).format(minor / 100);
}
