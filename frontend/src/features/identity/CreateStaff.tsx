import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, identityApi, type Role } from "../../shared/api/identity";
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
import { Button } from "../../shared/ui/Button";
import { Input, PasswordInput, PhoneInput } from "../../shared/ui/Input";
import { Alert, Card, Toast } from "../../shared/ui/Feedback";
import { RoleFields } from "./RoleFields";
import type { AuthProps } from "./staff-types";

export function CreateStaff({ onExpired }: AuthProps) {
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
