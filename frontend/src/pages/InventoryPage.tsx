import { ReceivingBoard } from "../features/receiving/ReceivingBoard";
import { Directories } from "../features/receiving/Directories";
import { useCallback, useEffect, useState } from "react";
import { ApiError, identityApi, type Staff } from "../shared/api/identity";
import { PageShell } from "../shared/ui/PageShell";
import { Alert, ErrorState, LoadingState } from "../shared/ui/Feedback";
import { LoginForm } from "../features/identity/LoginForm";
import { InventoryBoard } from "../features/inventory/InventoryBoard";
import { inventoryRu as t } from "../shared/locales/inventory";
import { errorMessage } from "../shared/lib/forms";
export function InventoryPage() {
  const [user, setUser] = useState<Staff | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  const expire = useCallback(() => setUser(null), []);
  useEffect(() => {
    let active = true;
    void identityApi
      .me()
      .then((data) => {
        if (active) setUser(data);
      })
      .catch((cause) => {
        if (active && !(cause instanceof ApiError && cause.status === 401))
          setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  return (
    <PageShell staff user={user} navigation={<a href="/staff">{t.cabinet}</a>}>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          message={error}
          onRetry={() => {
            setLoading(true);
            setError("");
            setAttempt((value) => value + 1);
          }}
        />
      ) : !user ? (
        <LoginForm onLogin={setUser} />
      ) : !user.permissions.includes("inventory.manage") ? (
        <Alert>{t.forbidden}</Alert>
      ) : window.location.pathname === "/staff/receipts" ? (
        <ReceivingBoard onExpired={expire} />
      ) : window.location.pathname === "/staff/settings" ? (
        <Directories onExpired={expire} />
      ) : (
        <InventoryBoard onExpired={expire} />
      )}
    </PageShell>
  );
}
