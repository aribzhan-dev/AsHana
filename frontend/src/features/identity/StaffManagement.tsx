import { useEffect, useState } from "react";
import { identityApi, type Staff } from "../../shared/api/identity";
import { errorMessage } from "../../shared/lib/forms";
import { identityRu as t } from "../../shared/locales/identity";
import { Button, IconButton } from "../../shared/ui/Button";
import { Alert, Card } from "../../shared/ui/Feedback";
import { RoleManager } from "./RoleManager";
import type { AuthProps } from "./staff-types";
import { CreateStaff } from "./CreateStaff";
import { FindStaff } from "./FindStaff";
import { StaffDialog, type StaffMode } from "./StaffDialog";

export function StaffManagement({
  current,
  onExpired,
}: AuthProps & { current: Staff }) {
  const [tab, setTab] = useState("staff");
  const [members, setMembers] = useState<Staff[]>([]),
    [error, setError] = useState("");
  const [open, setOpen] = useState<{ member: Staff; mode: StaffMode } | null>(
    null,
  );
  const [roleNames, setRoleNames] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    void identityApi
      .listStaff(offset)
      .then((v) => {
        if (alive) {
          setMembers(v);
          setError("");
        }
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, [offset, attempt]);
  useEffect(() => {
    let alive = true;
    identityApi
      .listRoles()
      .then((list) => {
        if (alive)
          setRoleNames(Object.fromEntries(list.map((r) => [r.code, r.name])));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [attempt]);
  return (
    <div className="form-stack">
      <div className="stock-tabs">
        <Button
          variant={tab === "staff" ? "primary" : "secondary"}
          onClick={() => setTab("staff")}
        >
          Сотрудники
        </Button>
        <Button
          variant={tab === "roles" ? "primary" : "secondary"}
          onClick={() => setTab("roles")}
        >
          Роли и доступ
        </Button>
      </div>
      {tab === "roles" ? (
        <RoleManager onSaved={() => setAttempt((n) => n + 1)} />
      ) : (
        <>
          <Card>
            <div className="stock-heading">
              <h2>Все сотрудники</h2>
              <Button
                variant="secondary"
                onClick={() => setAttempt((n) => n + 1)}
              >
                Обновить
              </Button>
            </div>
            {error && <Alert>{error}</Alert>}
            <div className="staff-directory">
              {members.map((member) => {
                const label = member.nickname || member.name;
                const self = member.id === current.id;
                return (
                  <div key={member.id}>
                    <span>
                      <strong>
                        {label}
                        {!member.is_active && (
                          <span className="status-badge">Заблокирован</span>
                        )}
                      </strong>
                      <small>
                        {[member.login, member.phone, member.telegram]
                          .filter(Boolean)
                          .join(" · ")}
                      </small>
                    </span>
                    <span className="row-actions">
                      <IconButton
                        variant="ghost"
                        icon="eye"
                        label={`Просмотр: ${label}`}
                        onClick={() => setOpen({ member, mode: "view" })}
                      />
                      <IconButton
                        variant="ghost"
                        icon="edit"
                        label={`Изменить: ${label}`}
                        onClick={() => setOpen({ member, mode: "edit" })}
                      />
                      <IconButton
                        variant="ghost"
                        icon="trash"
                        label={`Удалить: ${label}`}
                        disabled={self}
                        onClick={() => setOpen({ member, mode: "delete" })}
                      />
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="button-row">
              <Button
                variant="secondary"
                disabled={!offset}
                onClick={() => setOffset(offset - 100)}
              >
                Назад
              </Button>
              <Button
                variant="secondary"
                disabled={members.length < 100}
                onClick={() => setOffset(offset + 100)}
              >
                Далее
              </Button>
            </div>
          </Card>
          <section className="staff-admin" aria-label={t.management}>
            <CreateStaff onExpired={onExpired} />
            <FindStaff
              onExpired={onExpired}
              onFound={(member) => setOpen({ member, mode: "view" })}
            />
          </section>
        </>
      )}
      {open && (
        <StaffDialog
          key={open.member.id}
          member={open.member}
          current={current}
          mode={open.mode}
          roleNames={roleNames}
          onMode={(mode) => setOpen({ ...open, mode })}
          onClose={() => setOpen(null)}
          onChanged={() => setAttempt((n) => n + 1)}
          onExpired={onExpired}
        />
      )}
    </div>
  );
}
