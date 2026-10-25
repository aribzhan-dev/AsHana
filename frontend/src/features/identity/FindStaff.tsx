import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, identityApi, type Staff } from "../../shared/api/identity";
import { loginError } from "../../shared/lib/identity-validation";
import {
  errorMessage,
  fieldMessages,
  focusInvalid,
} from "../../shared/lib/forms";
import { identityRu as t } from "../../shared/locales/identity";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { Alert, Card } from "../../shared/ui/Feedback";
import type { AuthProps } from "./staff-types";

export function FindStaff({
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
