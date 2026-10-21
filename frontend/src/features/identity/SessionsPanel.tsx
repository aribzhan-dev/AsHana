import { useEffect, useState } from "react";
import {
  ApiError,
  identityApi,
  type StaffSession,
} from "../../shared/api/identity";
import { errorMessage } from "../../shared/lib/forms";
import { identityRu as t } from "../../shared/locales/identity";
import { uiRu as ui } from "../../shared/locales/ui";
import { Button } from "../../shared/ui/Button";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
import { Icon } from "../../shared/ui/Icon";

const date = (value: string) =>
  new Intl.DateTimeFormat("ru-KZ", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Almaty",
  }).format(new Date(value));
export function SessionsPanel({ onExpired }: { onExpired: () => void }) {
  const [sessions, setSessions] = useState<StaffSession[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<StaffSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  useEffect(() => {
    let active = true;
    void identityApi
      .sessions()
      .then((data) => {
        if (active) setSessions(data);
      })
      .catch((cause) => {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 401) onExpired();
        else setError(errorMessage(cause));
      });
    return () => {
      active = false;
    };
  }, [attempt, onExpired]);
  async function revoke() {
    if (!selected || busy) return;
    setBusy(true);
    setActionError("");
    try {
      await identityApi.revoke(selected.id);
      if (selected.current) onExpired();
      else {
        setSessions(
          (previous) =>
            previous?.filter((item) => item.id !== selected.id) || [],
        );
        setSelected(null);
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else setActionError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <div className="section-heading">
        <span className="section-icon">
          <Icon name="monitor" />
        </span>
        <h2>{t.sessions}</h2>
      </div>
      <p className="muted">{t.sessionHint}</p>
      {error ? (
        <ErrorState
          message={error}
          onRetry={() => {
            setError("");
            setSessions(null);
            setAttempt((value) => value + 1);
          }}
        />
      ) : !sessions ? (
        <LoadingState />
      ) : !sessions.length ? (
        <EmptyState title={t.empty} />
      ) : (
        <ul className="sessions">
          {sessions.map((session) => (
            <li key={session.id}>
              <div className="session-info">
                <strong>{session.current ? t.current : t.other}</strong>
                {session.current && <Badge>{t.current}</Badge>}
                <dl>
                  <div>
                    <dt>{t.started}</dt>
                    <dd>{date(session.created_at)}</dd>
                  </div>
                  <div>
                    <dt>{t.expires}</dt>
                    <dd>{date(session.expires_at)}</dd>
                  </div>
                </dl>
              </div>
              <Button
                variant="secondary"
                onClick={() => {
                  setActionError("");
                  setSelected(session);
                }}
              >
                {t.revoke}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <Dialog
        open={!!selected}
        title={ui.revokeTitle}
        description={ui.revokeDescription}
        onClose={() => setSelected(null)}
        busy={busy}
      >
        {actionError && <Alert>{actionError}</Alert>}
        <div className="dialog-actions">
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => setSelected(null)}
          >
            {ui.cancel}
          </Button>
          <Button variant="danger" loading={busy} onClick={() => void revoke()}>
            {t.revoke}
          </Button>
        </div>
      </Dialog>
    </Card>
  );
}
