import { expect, it } from "vitest";
import { formatExpiry, validateTestCard } from "../src/shared/lib/test-card";

const now = new Date(2026, 9, 23);
// Feeds characters one by one, the way the input re-formats each keystroke.
const typed = (keys: string) =>
  [...keys].reduce((value, key) => formatExpiry(value + key, now), "");

it("месяц срока карты — только 01–12", () => {
  expect(typed("13")).toBe("1");
  expect(typed("00")).toBe("0");
  expect(typed("12")).toBe("12");
  expect(typed("5")).toBe("05");
  // After an auto-filled "09" the next digit already belongs to the year.
  expect(typed("99")).toBe("09/9");
});

it("год срока карты — не раньше текущего", () => {
  expect(typed("1225")).toBe("12/2");
  expect(typed("121")).toBe("12");
  expect(typed("1226")).toBe("12/26");
  expect(typed("0931")).toBe("09/31");
  // A pasted four-digit year is cut to YY digits, so "2026" reads as "20".
  expect(formatExpiry("12/2026", now)).toBe("12/2");
});

it("истёкший месяц текущего года отклоняется при оплате", () => {
  const card = "4242 4242 4242 4242";
  expect(validateTestCard(card, "09/26", "123", now).errors.expiry).toBe(
    "Срок действия карты истёк",
  );
  expect(validateTestCard(card, "10/26", "123", now).outcome).toBe("success");
});
