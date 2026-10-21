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
} from "../../shared/lib/identity-validation";
import {
  errorMessage,
  fieldMessages,
  focusInvalid,
} from "../../shared/lib/forms";
import { identityRu as t } from "../../shared/locales/identity";
import { uiRu as ui } from "../../shared/locales/ui";
import { Button } from "../../shared/ui/Button";
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
        password,
        roles,
      });
      setName("");
      setNickname("");
      setLogin("");
      setPhone("");
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
      <h3>{target.nickname || target.name}</h3>
      <NicknameEditor
        target={target}
        onUpdated={onUpdated}
        onExpired={onExpired}
      />
      <p className="muted">
        {target.login}
        {target.phone && <> · {target.phone}</>}
      </p>
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
function FindStaff({ current, onExpired }: AuthProps & { current: Staff }) {
  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<Staff | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldError, setFieldError] = useState("");
  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const invalid = loginError(query);
    setFieldError(invalid || "");
    setTarget(null);
    setError("");
    if (invalid) {
      focusInvalid(event.currentTarget);
      return;
    }
    setBusy(true);
    try {
      setTarget(await identityApi.search(query));
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
            setTarget(null);
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
      {target && (
        <EditRoles
          key={target.id}
          current={current}
          target={target}
          onUpdated={setTarget}
          onExpired={onExpired}
        />
      )}
    </Card>
  );
}
export function StaffManagement({
  current,
  onExpired,
}: AuthProps & { current: Staff }) {
  const [tab, setTab] = useState("staff");
  const [members, setMembers] = useState<Staff[]>([]),
    [error, setError] = useState("");
  const [selected, setSelected] = useState<Staff | null>(null),
    [offset, setOffset] = useState(0),
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
              {members.map((member) => (
                <div key={member.id}>
                  <span>
                    <strong>{member.nickname || member.name}</strong>
                    <small>{member.login}</small>
                  </span>
                  <Button
                    variant="secondary"
                    onClick={() => setSelected(member)}
                  >
                    Доступ
                  </Button>
                </div>
              ))}
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
            <FindStaff current={current} onExpired={onExpired} />
          </section>
        </>
      )}
      {selected && (
        <Dialog
          open
          title="Доступ сотрудника"
          onClose={() => setSelected(null)}
        >
          <EditRoles
            key={selected.id}
            target={selected}
            current={current}
            onUpdated={(user) => {
              setSelected(user);
              setAttempt((n) => n + 1);
            }}
            onExpired={onExpired}
          />
        </Dialog>
      )}
    </div>
  );
}

function NicknameEditor({
  target,
  onUpdated,
  onExpired,
}: AuthProps & { target: Staff; onUpdated: (v: Staff) => void }) {
  const [nickname, setNickname] = useState(target.nickname || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      onUpdated(
        await identityApi.nickname(target.id, nickname, target.nickname || ""),
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onExpired();
      else setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="form-stack">
      <Input
        label="Никнейм"
        value={nickname}
        maxLength={100}
        onChange={(e) => setNickname(e.target.value)}
        hint="Отображается в истории операций вместо ID."
      />
      <Button
        variant="secondary"
        loading={busy}
        disabled={nickname === (target.nickname || "")}
        onClick={() => void save()}
      >
        Сохранить никнейм
      </Button>
      {error && <Alert>{error}</Alert>}
    </div>
  );
}
