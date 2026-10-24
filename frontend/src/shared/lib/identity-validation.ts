import { parsePhoneNumberFromString } from "libphonenumber-js/max";
import { identityRu as t } from "../locales/identity";

export function phoneError(value: string): string | undefined {
  if (!/^[+0-9 ()-]{1,32}$/.test(value)) return t.phoneError;
  const compact = value.replace(/[ ()-]/g, "");
  const phone = parsePhoneNumberFromString(compact);
  if (
    !/^\+7\d{10}$/.test(compact) ||
    !phone?.isValid() ||
    phone.country !== "KZ" ||
    phone.getType() !== "MOBILE"
  )
    return t.phoneError;
}
export function nameError(value: string): string | undefined {
  const name = value.trim().normalize("NFC");
  if (
    /\p{C}/u.test(value) ||
    [...name].length > 100 ||
    !/^\p{L}[\p{L}\p{M}]*(?:[ '\u2019-]\p{L}[\p{L}\p{M}]*)*$/u.test(name)
  )
    return t.nameError;
}
export function passwordError(value: string): string | undefined {
  if ([...value].length < 4 || [...value].length > 128) return t.passwordError;
}

export function loginError(value: string): string | undefined {
  if (!/^[A-Za-z][A-Za-z0-9._-]{2,39}$/.test(value.replace(/^ +| +$/g, "")))
    return t.loginError;
}

// Telegram username: optional, @ plus 5–32 latin letters, digits or underscores.
export function telegramError(value: string): string | undefined {
  const name = value
    .trim()
    .replace(/^https:\/\/t\.me\//, "")
    .replace(/^@/, "");
  if (!name) return undefined;
  if (!/^[A-Za-z0-9_]{5,32}$/.test(name))
    return "Telegram: @ и 5–32 латинских буквы, цифры или подчёркивания";
  return undefined;
}
