import { useCallback, useEffect, useState } from "react";
import { ApiError, identityApi, type Staff } from "../shared/api/identity";
import { PageShell } from "../shared/ui/PageShell";
import { Alert, ErrorState, LoadingState } from "../shared/ui/Feedback";
import { LoginForm } from "../features/identity/LoginForm";
import { FinanceBoard } from "../features/finance/FinanceBoard";

import { catalogRu as t } from "../shared/locales/catalog";
import { errorMessage } from "../shared/lib/forms";
export function FinancePage() {
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
      ) : !user.permissions.includes("finance.manage") ? (
        <Alert>Финансы доступны управляющему.</Alert>
      ) : (
        <>
          <div className="page-heading">
            <h1>Финансы</h1>
          </div>
          <FinanceBoard onExpired={expire} />
        </>
      )}
    </PageShell>
  );
}
