import { costMinor, decimalText } from "./inventory-validation";
// Round each positive line to a whole tiyn exactly, matching Decimal ROUND_HALF_UP.
export function invoiceLineCost(
  quantity: string,
  price: string,
): number | undefined {
  const value = decimalText(quantity),
    minor = costMinor(price);
  if (!/^\d{1,12}(\.\d{1,3})?$/.test(value) || minor === undefined)
    return undefined;
  const [whole, fraction = ""] = value.split(".");
  const scaled = BigInt(whole!) * 1000n + BigInt(fraction.padEnd(3, "0"));
  const result = (scaled * BigInt(minor) + 500n) / 1000n;
  return result <= 999999999999n ? Number(result) : undefined;
}
