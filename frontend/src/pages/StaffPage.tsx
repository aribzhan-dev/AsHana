import { useCallback, useEffect, useState } from "react";
import { ApiError, identityApi, type Staff } from "../shared/api/identity";
import { errorMessage } from "../shared/lib/forms";
import { identityRu as t } from "../shared/locales/identity";
import { Button } from "../shared/ui/Button";
import {
  Alert,
  Badge,
  Card,
  ErrorState,
  LoadingState,
} from "../shared/ui/Feedback";
import { PageShell } from "../shared/ui/PageShell";
import { LoginForm } from "../features/identity/LoginForm";
import { StaffManagement } from "../features/identity/StaffManagement";
import { Dashboard } from "../features/reporting/Dashboard";
import { SessionsPanel } from "../features/identity/SessionsPanel";
import { MyShift } from "../features/finance/MyShift";

function Cabinet({ user, onExpired }: { user: Staff; onExpired: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function logout() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await identityApi.logout();
      onExpired();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  const section = window.location.pathname;
  if (section === "/staff")
    return (
      <>
        <MyShift />
        <Dashboard user={user} onExpired={onExpired} />
      </>
    );
  if (section === "/staff/team")
    return (
      <>
        <h1>Сотрудники и доступ</h1>
        {user.permissions.includes("identity.manage") ? (
          <StaffManagement current={user} onExpired={onExpired} />
        ) : (
          <Alert>Управление сотрудниками доступно администратору.</Alert>
        )}
      </>
    );
  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">{t.team}</p>
        <h1>Профиль</h1>
      </div>
      <MyShift />
      <Card className="profile">
        <div>
          <h2>{user.name}</h2>
          <p className="muted">
            {user.login}
            {user.phone && <> · {user.phone}</>}
          </p>
          <div className="badges">
            {user.roles.map((role) => (
              <Badge key={role}>
                {(t.roleLabels as Record<string, string>)[role] || role}
              </Badge>
            ))}
          </div>
        </div>
        <Button
          variant="secondary"
          icon="logout"
          loading={busy}
          onClick={() => void logout()}
        >
          {t.logout}
        </Button>
        {error && <Alert>{error}</Alert>}
      </Card>
      <SessionsPanel onExpired={onExpired} />
    </>
  );
}
export function StaffPage() {
  const [user, setUser] = useState<Staff | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
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
    <PageShell staff user={user} navigation={<a href="/">{t.guest}</a>}>
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
      ) : user ? (
        <Cabinet user={user} onExpired={expire} />
      ) : (
        <LoginForm onLogin={setUser} />
      )}
    </PageShell>
  );
}
