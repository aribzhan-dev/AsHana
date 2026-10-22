// Payload shown to the guest and read by the counter scanner.
// The code is still verified by the server; the QR only removes manual typing.
const PREFIX = "ASHANA1";
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CODE = /^[0-9A-F]{8}$/;

export type PickupScan = { orderId: string; code: string };

export function pickupPayload(orderId: string, code: string): string {
  return `${PREFIX}:${orderId}:${code}`;
}

export function parsePickupPayload(raw: string): PickupScan | null {
  const [prefix, orderId = "", code = "", ...rest] = raw.trim().split(":");
  if (prefix?.toUpperCase() !== PREFIX || rest.length) return null;
  const normalized = code.toUpperCase();
  if (!ID.test(orderId) || !CODE.test(normalized)) return null;
  return { orderId: orderId.toLowerCase(), code: normalized };
}

// Short human-friendly order number derived from the UUID, as in the mockup.
export function orderNumber(orderId: string): string {
  return String(
    parseInt(orderId.replace(/-/g, "").slice(0, 6), 16) % 10000,
  ).padStart(4, "0");
}
