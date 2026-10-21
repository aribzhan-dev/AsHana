import { useEffect, useState } from "react";
import { ApiError, identityApi, type Staff } from "../shared/api/identity";
import { PageShell } from "../shared/ui/PageShell";
import { Alert, ErrorState, LoadingState } from "../shared/ui/Feedback";
import { LoginForm } from "../features/identity/LoginForm";
import { OrderList } from "../features/orders/OrderList";
import { SlotManager } from "../features/orders/SlotManager";
import { catalogRu as t } from "../shared/locales/catalog";
import { errorMessage } from "../shared/lib/forms";
export function StaffOrdersPage() {
  const [user, setUser] = useState<Staff | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);

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
      ) : !user.permissions.includes("kitchen.read") ? (
        <Alert>Заказы доступны кухне, кассиру и управляющему.</Alert>
      ) : (
        <>
          <div className="page-heading">
            <h1>Входящие заказы</h1>
          </div>
          <p>
            Готовые блюда порционируют по заказу. Ближайшее время получения —
            первым.
          </p>
          <OrderList staff permissions={user.permissions} />
          {user.permissions.includes("catalog.manage") && (
            <details className="card">
              <summary>Настройка времени получения</summary>
              <SlotManager />
            </details>
          )}
        </>
      )}
    </PageShell>
  );
}
