import { CashWriteOff } from "../features/pos/CashWriteOff";
import { Button } from "../shared/ui/Button";
import { SalesHistory } from "../features/pos/SalesHistory";
import { useCallback, useEffect, useState } from "react";
import { ApiError, identityApi, type Staff } from "../shared/api/identity";
import { PageShell } from "../shared/ui/PageShell";
import { Alert, ErrorState, LoadingState } from "../shared/ui/Feedback";
import { LoginForm } from "../features/identity/LoginForm";
import { PosBoard } from "../features/pos/PosBoard";

import { catalogRu as t } from "../shared/locales/catalog";
import { errorMessage } from "../shared/lib/forms";
export function PosPage() {
  const [tab, setTab] = useState("sale");
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
      ) : !user.permissions.includes("pos.sell") ? (
        <Alert>Касса доступна кассиру и управляющему.</Alert>
      ) : window.location.pathname === "/staff/sales" ? (
        <SalesHistory permissions={user.permissions} />
      ) : (
        <>
          <div className="page-heading">
            <h1>Касса</h1>
          </div>
          <div className="stock-tabs">
            <Button
              variant={tab === "sale" ? "primary" : "secondary"}
              onClick={() => setTab("sale")}
            >
              Продажа
            </Button>
            {user.permissions.some((p) =>
              ["inventory.manage", "inventory.writeoff"].includes(p),
            ) && (
              <Button
                variant={tab === "writeoff" ? "primary" : "secondary"}
                onClick={() => setTab("writeoff")}
              >
                Списание
              </Button>
            )}
            <a href="/staff/sales">История продаж</a>
          </div>
          <div hidden={tab !== "sale"}>
            <PosBoard userId={user.id} onExpired={expire} />
          </div>
          {tab === "writeoff" && <CashWriteOff onExpired={expire} />}
        </>
      )}
    </PageShell>
  );
}
