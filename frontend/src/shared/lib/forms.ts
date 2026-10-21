import { ApiError } from "../api/identity";
import { identityRu as t } from "../locales/identity";

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : t.genericError;
}
export function fieldMessages(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  return Object.fromEntries(
    Object.entries(error.fields).map(([key, messages]) => [
      key,
      messages.join(". "),
    ]),
  );
}
export function focusInvalid(form: HTMLFormElement): void {
  requestAnimationFrame(() =>
    form
      .querySelector<HTMLElement>(
        'input[aria-invalid="true"], select[aria-invalid="true"], fieldset[aria-invalid="true"] input',
      )
      ?.focus(),
  );
}
