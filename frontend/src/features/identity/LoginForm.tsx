import { useState } from "react";
import type { FormEvent } from "react";
import { identityApi, type Staff } from "../../shared/api/identity";
import { loginError } from "../../shared/lib/identity-validation";
import {
  errorMessage,
  fieldMessages,
  focusInvalid,
} from "../../shared/lib/forms";
import { identityRu as t } from "../../shared/locales/identity";
import { Button } from "../../shared/ui/Button";
import { Input, PasswordInput } from "../../shared/ui/Input";
import { Alert, Card } from "../../shared/ui/Feedback";

export function LoginForm({ onLogin }: { onLogin: (user: Staff) => void }) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const invalid = {
      login: loginError(login) || "",
      password: !password
        ? t.passwordRequired
        : [...password].length > 128
          ? t.passwordError
          : "",
    };
    setFields(invalid);
    setError("");
    if (Object.values(invalid).some(Boolean)) {
      focusInvalid(form);
      return;
    }
    setBusy(true);
    try {
      onLogin(await identityApi.login(login, password));
    } catch (cause) {
      setFields(fieldMessages(cause));
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-layout">
      <div className="login-intro">
        <p className="eyebrow">{t.team}</p>
        <h1>{t.title}</h1>
        <p className="description">{t.loginDescription}</p>
      </div>
      <Card className="login-card">
        <h2>{t.login}</h2>
        <p className="muted">{t.intro}</p>
        <form
          onSubmit={(event) => void submit(event)}
          noValidate
          aria-label={t.login}
        >
          <fieldset className="form-fields" disabled={busy}>
            <Input
              label={t.loginLabel}
              name="login"
              value={login}
              onChange={(event) => setLogin(event.target.value)}
              placeholder={t.loginPlaceholder}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              leadingIcon="user"
              required
              maxLength={64}
              error={fields.login}
            />
            <PasswordInput
              label={t.password}
              name="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={t.passwordPlaceholder}
              autoComplete="current-password"
              required
              maxLength={256}
              error={fields.password}
            />
          </fieldset>
          {error && <Alert>{error}</Alert>}
          <Button type="submit" loading={busy} className="full-width">
            {busy ? t.saving : t.login}
          </Button>
        </form>
      </Card>
    </div>
  );
}
