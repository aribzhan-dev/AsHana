import { useState } from "react";
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
import { RoleFields } from "./RoleFields";

type AuthProps = { onExpired: () => void };
function CreateStaff({ onExpired }: AuthProps) {
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
        login,
        phone: phone || null,
        password,
        roles,
      });
      setName("");
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
      <p className="muted">{t.intro}</p>
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
            onChange={(event) => setName(event.target.value)}
            placeholder={t.namePlaceholder}
            autoComplete="off"
            required
            maxLength={200}
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
      <h3>{target.name}</h3>
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
  return (
    <section className="staff-admin" aria-label={t.management}>
      <CreateStaff onExpired={onExpired} />
      <FindStaff current={current} onExpired={onExpired} />
    </section>
  );
}
