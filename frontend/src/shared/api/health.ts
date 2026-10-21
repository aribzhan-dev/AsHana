import type { components } from "./schema";

type HealthResponse = components["schemas"]["HealthResponse"];

function isHealthResponse(value: unknown): value is HealthResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    value.status === "ok" &&
    "service" in value &&
    value.service === "ashana-api"
  );
}

export async function checkReadiness(signal: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch("/api/v1/health/ready", {
      signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return false;
    const body: unknown = await response.json();
    return isHealthResponse(body);
  } catch {
    return false;
  }
}
