import { useRef, useState } from "react";
import { ApiError } from "../api/http";
import { errorMessage, fieldMessages } from "./forms";
import { inventoryRu as t } from "../locales/inventory";

export function useOperation(onExpired: () => void) {
  const pending = useRef<{ body: string; key: string } | null>(null);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  async function run(
    body: unknown,
    action: (key: string) => Promise<unknown>,
  ): Promise<boolean> {
    if (inFlight.current) return false;
    const serialized = JSON.stringify(body);
    if (pending.current?.body !== serialized)
      pending.current = { body: serialized, key: crypto.randomUUID() };
    inFlight.current = true;
    setBusy(true);
    setError("");
    setFields({});
    try {
      await action(pending.current.key);
      pending.current = null;
      return true;
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else {
        setFields(fieldMessages(cause));
        setError(
          cause instanceof ApiError && cause.status === 0
            ? t.networkNotice
            : errorMessage(cause),
        );
      }
      return false;
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return { busy, error, fields, setFields, setError, run };
}
