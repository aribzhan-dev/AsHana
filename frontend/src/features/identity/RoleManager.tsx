import { permissionLabels } from "../../shared/locales/permissions";
import { useEffect, useState } from "react";
import { identityApi, type RoleDefinition } from "../../shared/api/identity";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { CheckboxGroup } from "../../shared/ui/CheckboxGroup";
import { Alert, Card, LoadingState } from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
import { errorMessage } from "../../shared/lib/forms";
export function RoleManager({ onSaved }: { onSaved: () => void }) {
  const [roles, setRoles] = useState<RoleDefinition[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<RoleDefinition | null>(null),
    [busy, setBusy] = useState(false),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    void identityApi
      .listRoles()
      .then((v) => {
        if (alive) setRoles(v);
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [attempt]);
  async function save() {
    if (!editing || busy) return;
    setBusy(true);
    setError("");
    try {
      await identityApi.saveRole(editing);
      setEditing(null);
      setAttempt((n) => n + 1);
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="form-stack">
      <div className="stock-heading">
        <h2>Роли и права доступа</h2>
        <Button
          icon="plus"
          onClick={() =>
            setEditing({ code: "", name: "", permissions: [], version: null })
          }
        >
          Создать роль
        </Button>
      </div>
      {error && !editing && <Alert>{error}</Alert>}
      {loading ? (
        <LoadingState />
      ) : (
        <div className="role-cards">
          {roles.map((r) => (
            <Card key={r.code}>
              <div className="stock-heading">
                <h3>{r.name}</h3>
                <Button variant="secondary" onClick={() => setEditing(r)}>
                  Изменить
                </Button>
              </div>
              <ul className="permission-list">
                {r.permissions.map((p) => (
                  <li key={p}>{permissionLabels[p] || p}</li>
                ))}
              </ul>
              {!r.permissions.length && (
                <p className="muted">Доступ только к своему профилю</p>
              )}
            </Card>
          ))}
        </div>
      )}
      {editing && (
        <Dialog
          open
          title={editing.version ? "Изменить роль" : "Новая роль"}
          busy={busy}
          onClose={() => setEditing(null)}
        >
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <Input
              label="Название роли"
              required
              maxLength={100}
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
            />
            <Input
              label="Код роли"
              hint="3–20 латинских букв, цифр и подчёркиваний, начиная с буквы."
              required
              disabled={!!editing.version}
              pattern="[a-z][a-z0-9_]{2,19}"
              maxLength={20}
              value={editing.code}
              onChange={(e) => setEditing({ ...editing, code: e.target.value })}
            />
            <CheckboxGroup
              label="Что может сотрудник"
              value={editing.permissions}
              options={Object.entries(permissionLabels).map(
                ([value, label]) => ({ value, label }),
              )}
              onChange={(permissions) =>
                setEditing({ ...editing, permissions })
              }
            />
            <p className="field-hint">
              При изменении прав сотрудники с этой ролью войдут заново.
              Администратору необходимо сохранить управление сотрудниками.
            </p>
            {error && <Alert>{error}</Alert>}
            <Button type="submit" loading={busy}>
              Сохранить роль
            </Button>
          </form>
        </Dialog>
      )}
    </section>
  );
}
