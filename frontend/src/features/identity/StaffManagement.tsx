import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  ApiError,
  identityApi,
  type Role,
  type Staff,
} from "../../shared/api/identity";
import {
  loginError,
  nameError,
  passwordError,
  phoneError,
  telegramError,
} from "../../shared/lib/identity-validation";
import {
  errorMessage,
  fieldMessages,
  focusInvalid,
} from "../../shared/lib/forms";
import { identityRu as t } from "../../shared/locales/identity";
import { uiRu as ui } from "../../shared/locales/ui";
import { Button, IconButton } from "../../shared/ui/Button";
import { Input, PasswordInput, PhoneInput } from "../../shared/ui/Input";
import { Alert, Card, Toast } from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
import { RoleManager } from "./RoleManager";
import { RoleFields } from "./RoleFields";

type AuthProps = { onExpired: () => void };
function CreateStaff({ onExpired }: AuthProps) {
  const [nickname, setNickname] = useState("");
  const [name, setName] = useState("");
  const [login, setLogin] = useState("");
  const [phone, setPhone] = useState("");
  const [telegram, setTelegram] = useState("");
  const [password, setPassword] = useState("");
  const [roles, setRoles] = useState<Role[]>(["kitchen"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>({});
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const invalid = {
      name: nameError(name) || "",
      login: loginError(login) || "",
      phone: phone ? phoneError(phone) || "" : "",
      telegram: telegramError(telegram) || "",
      password: passwordError(password) || "",
      roles: roles.length ? "" : t.roleError,
    };
    setFields(invalid);
    setError("");
    setNotice(false);
    if (Object.values(invalid).some(Boolean)) {
      focusInvalid(form);
      return;
    }
    setBusy(true);
    try {
      await identityApi.create({
        name,
        nickname,
        login,
        phone: phone || null,
        telegram: telegram || null,
        password,
        roles,
      });
      setName("");
      setNickname("");
      setLogin("");
      setPhone("");
      setTelegram("");
      setPassword("");
      setRoles(["kitchen"]);
      setFields({});
      setNotice(true);
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
    <Card>
      <h2>{t.create}</h2>
      <p className="muted">
        Создайте логин и пароль, затем выберите доступ сотрудника.
      </p>
      <form
        onSubmit={(event) => void submit(event)}
        noValidate
        aria-label={t.create}
      >
        <fieldset disabled={busy} className="form-fields">
          <Input
            label={t.name}
            name="name"
            value={name}
            onChange={(event) => {
              if (
                !/^[\p{L}\p{M} '’-]*$/u.test(event.target.value) &&
                !(event.nativeEvent as InputEvent).isComposing
              ) {
                setFields((current) => ({
                  ...current,
                  name: "Имя может содержать только буквы, пробел, дефис и апостроф",
                }));
                return;
              }
              setName(event.target.value);
              setFields((current) => ({
                ...current,
                name: nameError(event.target.value) || "",
              }));
            }}
            placeholder={t.namePlaceholder}
            autoComplete="off"
            required
            maxLength={100}
            error={fields.name}
          />
          <Input
            label={t.loginLabel}
            name="login"
            value={login}
            onChange={(event) => setLogin(event.target.value)}
            placeholder={t.loginPlaceholder}
            hint={t.loginHint}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            required
            maxLength={64}
            error={fields.login}
            leadingIcon="user"
          />
          <Input
            label="Никнейм"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            maxLength={100}
            hint="Имя для истории операций. Если не указано, показывается имя сотрудника."
            error={fields.nickname}
          />
          <PasswordInput
            label={t.password}
            name="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={t.createPasswordPlaceholder}
            hint={t.passwordHint}
            autoComplete="new-password"
            required
            maxLength={256}
            error={fields.password}
          />
          <PhoneInput
            label={t.phone}
            name="phone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            hint={t.phoneOptional}
            autoComplete="off"
            error={fields.phone}
          />
          <Input
            label="Telegram"
            name="telegram"
            value={telegram}
            onChange={(event) => setTelegram(event.target.value)}
            placeholder="@username"
            hint="Необязательно. Для связи с сотрудником."
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={60}
            error={fields.telegram}
          />
          <RoleFields value={roles} onChange={setRoles} error={fields.roles} />
        </fieldset>
        {error && <Alert>{error}</Alert>}
        {notice && <Toast onClose={() => setNotice(false)}>{t.created}</Toast>}
        <Button type="submit" icon="plus" loading={busy}>
          {busy ? t.saving : t.create}
        </Button>
      </form>
    </Card>
  );
}
function EditRoles({
  target,
  current,
  onUpdated,
  onExpired,
}: AuthProps & {
  target: Staff;
  current: Staff;
  onUpdated: (value: Staff) => void;
}) {
  const [assigned, setAssigned] = useState<Role[]>(target.roles);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(false);
  const changed =
    [...target.roles].sort().join() !== [...assigned].sort().join();
  async function save() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const updated = await identityApi.roles(target.id, assigned);
      setOpen(false);
      if (target.id === current.id) onExpired();
      else {
        onUpdated(updated);
        setNotice(true);
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="role-editor">
      {target.id !== current.id && (
        <PasswordReset target={target} onExpired={onExpired} />
      )}
      <RoleFields
        value={assigned}
        onChange={setAssigned}
        disabled={busy}
        error={!assigned.length ? t.roleError : undefined}
      />
      <p className="field-hint">{t.rolesHint}</p>
      {notice && <Toast onClose={() => setNotice(false)}>{t.rolesSaved}</Toast>}
      <Button
        disabled={!assigned.length || !changed || busy}
        onClick={() => {
          setError("");
          setOpen(true);
        }}
      >
        {t.saveRoles}
      </Button>
      <Dialog
        open={open}
        title={ui.rolesTitle}
        description={ui.rolesDescription}
        onClose={() => setOpen(false)}
        busy={busy}
      >
        {error && <Alert>{error}</Alert>}
        <div className="dialog-actions">
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => setOpen(false)}
          >
            {ui.cancel}
          </Button>
          <Button loading={busy} onClick={() => void save()}>
            {t.saveRoles}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
function FindStaff({
  onFound,
  onExpired,
}: AuthProps & { onFound: (found: Staff) => void }) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldError, setFieldError] = useState("");
  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const invalid = loginError(query);
    setFieldError(invalid || "");
    setError("");
    if (invalid) {
      focusInvalid(event.currentTarget);
      return;
    }
    setBusy(true);
    try {
      onFound(await identityApi.search(query));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else {
        setFieldError(fieldMessages(cause).login || "");
        setError(errorMessage(cause));
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <h2>{t.search}</h2>
      <p className="muted">{t.searchHint}</p>
      <form
        onSubmit={(event) => void search(event)}
        noValidate
        aria-label={t.search}
      >
        <Input
          label={t.loginLabel}
          name="search-login"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
          placeholder={t.loginPlaceholder}
          error={fieldError}
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          required
          maxLength={64}
          disabled={busy}
          leadingIcon="search"
        />
        {error && <Alert>{error}</Alert>}
        <Button type="submit" icon="search" loading={busy}>
          {t.search}
        </Button>
      </form>
    </Card>
  );
}
type StaffMode = "view" | "edit" | "delete";
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
function StaffDialog({
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

function PasswordReset({ target, onExpired }: AuthProps & { target: Staff }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldError, setFieldError] = useState("");
  const [notice, setNotice] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const invalid = passwordError(password) || "";
    setFieldError(invalid);
    setError("");
    setNotice(false);
    if (invalid) {
      focusInvalid(event.currentTarget);
      return;
    }
    setBusy(true);
    try {
      await identityApi.resetPassword(target.id, password);
      setPassword("");
      setNotice(true);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else {
        setFieldError(fieldMessages(cause).password || "");
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
      aria-label="Сброс пароля"
    >
      <PasswordInput
        label="Новый пароль"
        name="reset-password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        hint="Если сотрудник забыл пароль: задайте новый и сообщите его лично. Все его сессии завершатся."
        autoComplete="new-password"
        maxLength={256}
        error={fieldError}
        disabled={busy}
      />
      {error && <Alert>{error}</Alert>}
      {notice && (
        <Toast onClose={() => setNotice(false)}>
          Пароль изменён. Сотрудник входит с новым паролем.
        </Toast>
      )}
      <Button type="submit" variant="secondary" loading={busy}>
        Сбросить пароль
      </Button>
    </form>
  );
}
