import { identityRu as t } from "../locales/identity";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: Record<string, string[]> = {},
  ) {
    super(message);
  }
}
export function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
export function strings(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}
export async function request(
  path: string,
  method = "GET",
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<unknown> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  try {
    const headers: Record<string, string> = { ...extraHeaders };
    if (method !== "GET") {
      const csrf = await request("/auth/csrf");
      if (!record(csrf) || typeof csrf.csrf_token !== "string")
        throw new ApiError(0, t.genericError);
      headers["X-CSRF-Token"] = csrf.csrf_token;
    }
    // Files (photos) are sent as raw bytes with their own type; everything else is JSON.
    const binary = body instanceof Blob;
    if (binary) headers["Content-Type"] = body.type;
    else if (body !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch(`/api/v1${path}`, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers,
      signal: controller.signal,
      body:
        body === undefined ? undefined : binary ? body : JSON.stringify(body),
    });
    if (!response.ok) {
      const error: unknown = await response.json().catch(() => null);
      const fields: Record<string, string[]> = {};
      if (record(error) && record(error.field_errors)) {
        for (const [key, value] of Object.entries(error.field_errors))
          if (strings(value)) fields[key] = value;
      }
      throw new ApiError(
        response.status,
        record(error) && typeof error.message === "string"
          ? error.message
          : t.genericError,
        fields,
      );
    }
    const result: unknown =
      response.status === 204 ? undefined : await response.json();
    return result;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(0, t.networkError);
  } finally {
    window.clearTimeout(timeout);
  }
}
