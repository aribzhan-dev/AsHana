import { useState } from "react";
import type { FormEvent } from "react";
import {
  ApiError,
  identityApi,
  type Role,
  type Staff,
} from "../../shared/api/identity";
import { passwordError } from "../../shared/lib/identity-validation";
import {
  errorMessage,
  fieldMessages,
  focusInvalid,
} from "../../shared/lib/forms";
import { identityRu as t } from "../../shared/locales/identity";
import { uiRu as ui } from "../../shared/locales/ui";
import { Button } from "../../shared/ui/Button";
import { PasswordInput } from "../../shared/ui/Input";
import { Alert, Toast } from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
import { RoleFields } from "./RoleFields";
import type { AuthProps } from "./staff-types";

export function EditRoles({
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
