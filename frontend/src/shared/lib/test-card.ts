// Mock checkout accepts only published test card numbers. Card data never leaves
// the browser: the server receives just the simulated outcome (ADR-0003, ADR-0019).
export const TEST_CARDS = {
  "4242424242424242": "success",
  "5555555555554444": "success",
  "4000000000000002": "failed",
} as const;

export type TestCardOutcome = (typeof TEST_CARDS)[keyof typeof TEST_CARDS];

export function cardDigits(value: string): string {
  return value.replace(/\D/g, "").slice(0, 16);
}

export function formatCardNumber(value: string): string {
  return cardDigits(value).replace(/(\d{4})(?=\d)/g, "$1 ");
}

// Keeps only digits that can still form a valid MM/YY: month 01–12, year not before
// the current one. A first digit above 1 can only be a one-digit month ("5" → "05").
export function formatExpiry(value: string, now = new Date()): string {
  let digits = value.replace(/\D/g, "");
  if (/^[2-9]/.test(digits)) digits = `0${digits}`;
  digits = digits.slice(0, 4);
  const month = Number(digits.slice(0, 2));
  if (digits.length >= 2 && (month < 1 || month > 12))
    digits = digits.slice(0, 1);
  const minYear = now.getFullYear() % 100;
  if (digits.length >= 3 && Number(digits[2]) < Math.floor(minYear / 10))
    digits = digits.slice(0, 2);
  if (digits.length === 4 && Number(digits.slice(2)) < minYear)
    digits = digits.slice(0, 3);
  return digits.length > 2
    ? `${digits.slice(0, 2)}/${digits.slice(2)}`
    : digits;
}

function luhn(digits: string): boolean {
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    let n = Number(digits[digits.length - 1 - i]);
    if (i % 2) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    sum += n;
  }
  return sum % 10 === 0;
}

export type CardErrors = Partial<Record<"number" | "expiry" | "cvc", string>>;

export function validateTestCard(
  number: string,
  expiry: string,
  cvc: string,
  now = new Date(),
): { errors: CardErrors; outcome?: TestCardOutcome } {
  const errors: CardErrors = {};
  const digits = cardDigits(number);
  const outcome = TEST_CARDS[digits as keyof typeof TEST_CARDS];
  if (digits.length !== 16 || !luhn(digits))
    errors.number = "Введите 16 цифр номера карты";
  else if (!outcome)
    errors.number =
      "Это тестовая оплата: настоящие карты не принимаются. Используйте тестовую карту.";
  const match = /^(\d{2})\/(\d{2})$/.exec(expiry);
  const month = Number(match?.[1]);
  const year = 2000 + Number(match?.[2]);
  if (!match || month < 1 || month > 12)
    errors.expiry = "Укажите срок в формате ММ/ГГ";
  else if (
    year < now.getFullYear() ||
    (year === now.getFullYear() && month < now.getMonth() + 1)
  )
    errors.expiry = "Срок действия карты истёк";
  if (!/^\d{3}$/.test(cvc)) errors.cvc = "CVV — 3 цифры";
  return Object.keys(errors).length ? { errors } : { errors, outcome };
}
