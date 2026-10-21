import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../../shared/api/http";
import {
  productionApi,
  type Recipe,
  type RawBatch,
  type RawUnit,
} from "../../shared/api/production";
import { errorMessage, focusInvalid } from "../../shared/lib/forms";
import {
  almatyInstant,
  decimalText,
  stockDate,
  stockNumber,
  stockQuantityError,
} from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { inventoryRu as s } from "../../shared/locales/inventory";
import { productionRu as t } from "../../shared/locales/production";
import { Button } from "../../shared/ui/Button";
import { Alert, LoadingState } from "../../shared/ui/Feedback";
import { Input, Select } from "../../shared/ui/Input";
import {
  rawUnits,
  wholeError,
  yieldLabel,
} from "../../shared/lib/production-validation";

export function ProductionForm({
  recipe,
  onSaved,
  onExpired,
  onBusy,
}: {
  recipe: Recipe;
  onSaved: () => void;
  onExpired: () => void;
  onBusy: (busy: boolean) => void;
}) {
  const op = useOperation(onExpired);
  useEffect(() => {
    onBusy(op.busy);
  }, [op.busy, onBusy]);
  const [batches, setBatches] = useState<Record<string, RawBatch[]>>({}),
    [more, setMore] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true),
    [loadError, setLoadError] = useState(""),
    [attempt, setAttempt] = useState(0),
    [moreBusy, setMoreBusy] = useState(false);
  const [rows, setRows] = useState(() =>
    recipe.lines.map((l) => ({
      key: crypto.randomUUID(),
      item_id: l.item_id,
      batch_id: "",
      quantity: "",
      unit: l.unit as RawUnit,
    })),
  );
  const [label, setLabel] = useState(""),
    [actual, setActual] = useState(""),
    [expires, setExpires] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  useEffect(() => {
    let active = true;
    void Promise.all(
      recipe.lines.map(async (line) => ({
        id: line.item_id,
        data: await productionApi.batches(line.item_id),
      })),
    )
      .then((result) => {
        if (!active) return;
        setBatches(Object.fromEntries(result.map((r) => [r.id, r.data])));
        setMore(
          Object.fromEntries(result.map((r) => [r.id, r.data.length === 100])),
        );
      })
      .catch((cause) => {
        if (active) {
          if (cause instanceof ApiError && cause.status === 401) onExpired();
          else setLoadError(errorMessage(cause));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [recipe, onExpired, attempt]);
  async function loadMore(id: string) {
    setMoreBusy(true);
    setLoadError("");
    try {
      const next = await productionApi.batches(id, batches[id]?.length || 0);
      setBatches((current) => ({
        ...current,
        [id]: [...(current[id] || []), ...next],
      }));
      setMore((current) => ({ ...current, [id]: next.length === 100 }));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else setLoadError(errorMessage(cause));
    } finally {
      setMoreBusy(false);
    }
  }
  function patch(key: string, value: Partial<(typeof rows)[number]>) {
    setRows((current) =>
      current.map((r) => (r.key === key ? { ...r, ...value } : r)),
    );
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields: Record<string, string> = {};
    if (!label.trim()) fields.label = s.required;
    if (wholeError(actual)) fields.actual_yield = t.wholeError;
    const expiry = almatyInstant(expires);
    if (!expiry || Date.parse(expiry) <= Date.now())
      fields.expires_at = t.positiveExpiry;
    if (!confirmed) fields.suitability_confirmed = t.suitabilityError;
    for (const row of rows) {
      if (!row.batch_id) fields[`${row.key}-batch`] = s.required;
      const error = stockQuantityError(row.quantity, row.unit);
      if (error) fields[`${row.key}-quantity`] = error;
    }
    if (new Set(rows.map((r) => r.batch_id)).size !== rows.length)
      fields.consumption = t.duplicateBatch;
    op.setFields(fields);
    op.setError(fields.consumption || "");
    if (Object.keys(fields).length || !expiry) {
      focusInvalid(form);
      return;
    }
    const body = {
      recipe_id: recipe.id,
      label: label.trim(),
      actual_yield: Number(actual),
      expires_at: expiry,
      suitability_confirmed: confirmed,
      consumption: rows.map(({ batch_id, quantity, unit }) => ({
        batch_id,
        quantity: decimalText(quantity),
        unit,
      })),
    };
    if (await op.run(body, (key) => productionApi.produce(body, key)))
      onSaved();
    else focusInvalid(form);
  }
  return (
    <form className="form-stack" onSubmit={(e) => void submit(e)} noValidate>
      <div className="production-summary">
        <h3>
          {recipe.output_name} · {s.version} {recipe.version}
        </h3>
        <p>
          {t.expected}: {yieldLabel(recipe.expected_yield, recipe.output_unit)}
        </p>
        <p>{t.consumptionHint}</p>
      </div>
      {loading && <LoadingState />}
      {loadError && <Alert>{loadError}</Alert>}
      <Button
        variant="secondary"
        disabled={loading || op.busy || moreBusy}
        onClick={() => {
          setLoading(true);
          setLoadError("");
          setAttempt((n) => n + 1);
        }}
      >
        {t.refresh}
      </Button>
      <fieldset
        className="plain-fieldset form-stack"
        disabled={loading || op.busy || moreBusy}
      >
        {recipe.lines.map((line) => (
          <fieldset key={line.item_id} className="production-ingredient">
            <legend>{line.item_name}</legend>
            <p className="field-hint">
              {t.norm}: {stockNumber(line.quantity)}{" "}
              {s.units[line.unit as "kg" | "l"]}
            </p>
            {rows
              .filter((r) => r.item_id === line.item_id)
              .map((row, index) => (
                <div className="production-consumption" key={row.key}>
                  <Select
                    label={`${t.rawBatch} ${index + 1}`}
                    value={row.batch_id}
                    onChange={(e) =>
                      patch(row.key, { batch_id: e.target.value })
                    }
                    error={op.fields[`${row.key}-batch`]}
                    required
                  >
                    <option value="">{t.choose}</option>
                    {(batches[line.item_id] || []).map((b) => (
                      <option
                        key={b.id}
                        value={b.id}
                        disabled={
                          b.status !== "active" || Number(b.available) <= 0
                        }
                      >
                        {b.label} · {stockNumber(b.available)}{" "}
                        {s.units[b.unit as "kg" | "l"]} ·{" "}
                        {s.states[b.status as keyof typeof s.states]}
                      </option>
                    ))}
                  </Select>
                  {row.batch_id && (
                    <p className="field-hint">
                      {s.expires}:{" "}
                      {stockDate(
                        batches[line.item_id]?.find(
                          (b) => b.id === row.batch_id,
                        )?.expires_at || recipe.created_at,
                      )}
                    </p>
                  )}
                  <div className="stock-form-grid">
                    <Input
                      label={t.consumption}
                      inputMode="decimal"
                      maxLength={24}
                      value={row.quantity}
                      onChange={(e) =>
                        patch(row.key, { quantity: e.target.value })
                      }
                      error={op.fields[`${row.key}-quantity`]}
                      required
                    />
                    <Select
                      label={s.unit}
                      value={row.unit}
                      onChange={(e) =>
                        patch(row.key, { unit: e.target.value as RawUnit })
                      }
                    >
                      {rawUnits(line.unit).map((u) => (
                        <option key={u} value={u}>
                          {s.units[u]}
                        </option>
                      ))}
                    </Select>
                  </div>
                  {rows.filter((r) => r.item_id === line.item_id).length >
                    1 && (
                    <Button
                      variant="ghost"
                      onClick={() =>
                        setRows((current) =>
                          current.filter((r) => r.key !== row.key),
                        )
                      }
                    >
                      {t.removeBatch} {index + 1}
                    </Button>
                  )}
                </div>
              ))}
            {!loading &&
              !(batches[line.item_id] || []).some(
                (b) => b.status === "active" && Number(b.available) > 0,
              ) && <p className="field-hint">{t.unavailable}</p>}
            <div className="button-row">
              <Button
                variant="secondary"
                disabled={rows.length >= 100}
                onClick={() =>
                  setRows((current) => [
                    ...current,
                    {
                      key: crypto.randomUUID(),
                      item_id: line.item_id,
                      batch_id: "",
                      quantity: "",
                      unit: line.unit as RawUnit,
                    },
                  ])
                }
              >
                {t.addBatch}
              </Button>
              {more[line.item_id] && (
                <Button
                  variant="secondary"
                  onClick={() => void loadMore(line.item_id)}
                >
                  {t.moreBatches}
                </Button>
              )}
            </div>
          </fieldset>
        ))}
        <Input
          label={s.label}
          placeholder={t.labelPlaceholder}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          error={op.fields.label}
          maxLength={100}
          required
        />
        <Input
          label={t.actual}
          hint={s.units[recipe.output_unit as "pcs" | "portion"]}
          inputMode="numeric"
          maxLength={9}
          value={actual}
          onChange={(e) => setActual(e.target.value)}
          error={op.fields.actual_yield}
          required
        />
        <Input
          label={s.expires}
          hint={s.expiryHint}
          type="datetime-local"
          value={expires}
          onChange={(e) => setExpires(e.target.value)}
          error={op.fields.expires_at}
          required
        />
        <label className="production-confirm">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
            aria-invalid={!!op.fields.suitability_confirmed}
            aria-describedby={
              op.fields.suitability_confirmed ? "suitability-error" : undefined
            }
          />
          <span>{t.suitable}</span>
        </label>
        {op.fields.suitability_confirmed && (
          <p id="suitability-error" className="field-error">
            {op.fields.suitability_confirmed}
          </p>
        )}
      </fieldset>
      {op.error && <Alert>{op.error}</Alert>}
      <p className="field-hint">{t.confirmation}</p>
      <Button
        type="submit"
        loading={op.busy}
        disabled={loading || moreBusy || !!loadError}
      >
        {t.confirm}
      </Button>
      <p className="field-hint">{s.retryHint}</p>
    </form>
  );
}
