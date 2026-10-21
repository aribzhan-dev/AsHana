import type { RawUnit } from "../api/production";
import { productionRu as t } from "../locales/production";

export function rawUnits(unit: string): RawUnit[] {
  return unit === "l" || unit === "ml" ? ["l", "ml"] : ["kg", "g"];
}
export function wholeError(value: string) {
  return !/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 999999999
    ? t.wholeError
    : "";
}
// Present six-place stored quantities in smaller units without losing precision.
export function editableRaw(
  value: string,
  unit: string,
): { quantity: string; unit: RawUnit } {
  const [whole, fraction = ""] = value.split(".");
  const digits = `${whole}${fraction.padEnd(6, "0")}`;
  const small = BigInt(digits);
  return {
    quantity: `${small / 1000n}.${(small % 1000n).toString().padStart(3, "0")}`,
    unit: unit === "kg" ? "g" : "ml",
  };
}

export function yieldLabel(count: number, unit: string): string {
  const rule = new Intl.PluralRules("ru-RU").select(count);
  const label =
    unit === "pcs"
      ? t.pieces
      : t.portions[rule === "one" || rule === "few" ? rule : "many"];
  return `${count} ${label}`;
}
