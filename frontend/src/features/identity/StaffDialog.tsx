import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, identityApi, type Staff } from "../../shared/api/identity";
import {
  nameError,
  phoneError,
  telegramError,
} from "../../shared/lib/identity-validation";
import {
  errorMessage,
  fieldMessages,
  focusInvalid,
} from "../../shared/lib/forms";
import { identityRu as t } from "../../shared/locales/identity";
import { Button } from "../../shared/ui/Button";
import { Input, PhoneInput } from "../../shared/ui/Input";
import { Alert, Toast } from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
import type { AuthProps } from "./staff-types";
import { EditRoles } from "./StaffAccess";

export type StaffMode = "view" | "edit" | "delete";
const staffTitles: Record<StaffMode, string> = {
  view: "Сотрудник",
  edit: "Изменить сотрудника",
  delete: "Удалить сотрудника",
};
function telegramLink(handle: string) {
  return `https://t.me/${handle.replace(/^@/, "")}`;
}
function ProfileForm({
  target,
  onSaved,
  onExpired,
}: AuthProps & { target: Staff; onSaved: (value: Staff) => void }) {
  const [name, setName] = useState(target.name);
  const [nickname, setNickname] = useState(target.nickname || "");
  const [phone, setPhone] = useState(target.phone || "");
  const [telegram, setTelegram] = useState(target.telegram || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>({});
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const invalid = {
      name: nameError(name) || "",
      phone: phone ? phoneError(phone) || "" : "",
      telegram: telegramError(telegram) || "",
    };
    setFields(invalid);
    setError("");
    setNotice(false);
    if (Object.values(invalid).some(Boolean)) {
      focusInvalid(event.currentTarget);
      return;
    }
    setBusy(true);
    try {
      const saved = await identityApi.profile(target.id, {
        name,
        nickname,
        phone: phone || null,
        telegram: telegram || null,
      });
      setNotice(true);
      onSaved(saved);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else {
        setFields(fieldMessages(cause));
        setError(errorMessage(cause));
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="form-stack"
      onSubmit={(event) => void submit(event)}
      noValidate
      aria-label="Данные сотрудника"
    >
      <fieldset disabled={busy} className="form-fields">
        <Input
          label={t.name}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={100}
          error={fields.name}
        />
        <Input
          label="Никнейм"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          maxLength={100}
          hint="Имя для истории операций. Если не указано, показывается имя."
          error={fields.nickname}
        />
        <PhoneInput
          label={t.phone}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          hint={t.phoneOptional}
          autoComplete="off"
          error={fields.phone}
        />
        <Input
          label="Telegram"
          value={telegram}
          onChange={(e) => setTelegram(e.target.value)}
          placeholder="@username"
          hint="Необязательно. Для связи с сотрудником."
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          maxLength={60}
          error={fields.telegram}
        />
      </fieldset>
      {error && <Alert>{error}</Alert>}
      {notice && (
        <Toast onClose={() => setNotice(false)}>Данные сохранены</Toast>
      )}
      <Button type="submit" loading={busy}>
        Сохранить данные
      </Button>
    </form>
  );
}
export function StaffDialog({
  member,
  current,
  mode,
  roleNames,
  onMode,
  onClose,
  onChanged,
  onExpired,
}: AuthProps & {
  member: Staff;
  current: Staff;
  mode: StaffMode;
  roleNames: Record<string, string>;
  onMode: (mode: StaffMode) => void;
  onClose: () => void;
  onChanged: (value: Staff | null) => void;
}) {
  const [target, setTarget] = useState(member);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const self = target.id === current.id;
  useEffect(() => {
    let alive = true;
    void identityApi
      .member(member.id)
      .then((fresh) => alive && setTarget(fresh))
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) onExpired();
        else setError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, [member.id, onExpired]);
  async function act(action: () => Promise<Staff | null>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await action();
      if (result) setTarget(result);
      onChanged(result);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  const rows: [string, React.ReactNode][] = [
    ["Имя", target.name],
    ["Никнейм", target.nickname || "—"],
    ["Логин", target.login],
    ["Телефон", target.phone || "—"],
    [
      "Telegram",
      target.telegram ? (
        <a
          href={telegramLink(target.telegram)}
          target="_blank"
          rel="noreferrer"
        >
          {target.telegram}
        </a>
      ) : (
        "—"
      ),
    ],
    ["Роли", target.roles.map((r) => roleNames[r] || r).join(", ") || "—"],
    ["Статус", target.is_active ? "Активен" : "Заблокирован"],
    [
      "Создан",
      target.created_at
        ? new Date(target.created_at).toLocaleDateString("ru-RU", {
            timeZone: "Asia/Almaty",
          })
        : "—",
    ],
  ];
  return (
    <Dialog
      open
      title={`${staffTitles[mode]}: ${target.nickname || target.name}`}
      onClose={onClose}
      busy={busy}
    >
      {error && <Alert>{error}</Alert>}
      {mode === "view" && (
        <div className="form-stack">
          <dl className="staff-details">
            {rows.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          {self && (
            <p className="field-hint">
              Свой статус и доступ меняет другой администратор.
            </p>
          )}
          <div className="dialog-actions">
            <Button
              variant="secondary"
              icon="edit"
              onClick={() => onMode("edit")}
            >
              Изменить
            </Button>
            {!self && (
              <Button
                variant="secondary"
                loading={busy}
                onClick={() =>
                  void act(() =>
                    identityApi.status(target.id, !target.is_active),
                  )
                }
              >
                {target.is_active ? "Заблокировать" : "Разблокировать"}
              </Button>
            )}
            {!self && (
              <Button
                variant="danger"
                icon="trash"
                onClick={() => onMode("delete")}
              >
                Удалить
              </Button>
            )}
          </div>
        </div>
      )}
      {mode === "edit" && (
        <div className="form-stack">
          <ProfileForm
            key={target.id}
            target={target}
            onExpired={onExpired}
            onSaved={(saved) => {
              setTarget(saved);
              onChanged(saved);
            }}
          />
          <h3>Доступ и пароль</h3>
          <EditRoles
            key={`${target.id}-roles`}
            target={target}
            current={current}
            onUpdated={(saved) => {
              setTarget(saved);
              onChanged(saved);
            }}
            onExpired={onExpired}
          />
          <Button variant="secondary" onClick={() => onMode("view")}>
            Назад к карточке
          </Button>
        </div>
      )}
      {mode === "delete" && (
        <div className="form-stack">
          <p>
            Удалить сотрудника «{target.nickname || target.name}»? Он сразу
            выйдет из системы и не сможет войти. В истории операций имя
            сохранится, логин останется занятым.
          </p>
          <div className="dialog-actions">
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => onMode("view")}
            >
              Отмена
            </Button>
            <Button
              variant="danger"
              icon="trash"
              loading={busy}
              onClick={() =>
                void act(async () => {
                  await identityApi.remove(target.id);
                  onClose();
                  return null;
                })
              }
            >
              Удалить
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
