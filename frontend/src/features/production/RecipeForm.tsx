import { displayText } from "../../shared/lib/display-text";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../../shared/api/http";
import type { StockItem } from "../../shared/api/inventory";
import {
  productionApi,
  type Recipe,
  type RawUnit,
} from "../../shared/api/production";
import { errorMessage, focusInvalid } from "../../shared/lib/forms";
import {
  decimalText,
  stockQuantityError,
} from "../../shared/lib/inventory-validation";
import {
  rawUnits,
  wholeError,
  editableRaw,
} from "../../shared/lib/production-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { inventoryRu as s } from "../../shared/locales/inventory";
import { productionRu as t } from "../../shared/locales/production";
import { Button } from "../../shared/ui/Button";
import { Alert, LoadingState } from "../../shared/ui/Feedback";
import { Input, Select } from "../../shared/ui/Input";

export function RecipeForm({
  previous,
  onSaved,
  onExpired,
  onBusy,
}: {
  previous?: Recipe;
  onSaved: () => void;
  onExpired: () => void;
  onBusy: (busy: boolean) => void;
}) {
  const op = useOperation(onExpired);
  useEffect(() => {
    onBusy(op.busy);
  }, [op.busy, onBusy]);
  const [raw, setRaw] = useState<StockItem[]>([]),
    [outputs, setOutputs] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true),
    [loadError, setLoadError] = useState("");
  const [moreRaw, setMoreRaw] = useState(false),
    [moreOutput, setMoreOutput] = useState(false),
    [moreBusy, setMoreBusy] = useState(false);
  const [output, setOutput] = useState(previous?.output_item_id || ""),
    [expected, setExpected] = useState(
      previous ? String(previous.expected_yield) : "",
    );
  const initialPortion = previous
    ? editableRaw(previous.portion_quantity, previous.portion_unit)
    : { quantity: "", unit: "g" as RawUnit };
  const [portion, setPortion] = useState(initialPortion.quantity),
    [portionUnit, setPortionUnit] = useState<RawUnit>(initialPortion.unit);
  const [instructions, setInstructions] = useState(
    previous ? displayText(previous.instructions) : "",
  );
  const [lines, setLines] = useState(
    () =>
      previous?.lines.map((line) => ({
        key: crypto.randomUUID(),
        item_id: line.item_id,
        ...editableRaw(line.quantity, line.unit),
      })) || [
        {
          key: crypto.randomUUID(),
          item_id: "",
          quantity: "",
          unit: "kg" as RawUnit,
        },
      ],
  );
  const [rawPageCount, setRawPageCount] = useState(100);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    void Promise.all([
      productionApi.items("raw"),
      productionApi.items("prepared"),
    ])
      .then(([r, o]) => {
        if (!active) return;
        // Existing recipe items remain selectable even when outside the first catalogue page.
        const existing =
          previous?.lines.map((l) => ({
            id: l.item_id,
            name: l.item_name,
            unit: l.unit as "kg" | "l",
            kind: "raw" as const,
            category: "",
            purchase_price_minor: 0,
            sale_price_minor: 0,
            version: 1,
          })) || [];
        setRaw([
          ...r,
          ...existing.filter((l) => !r.some((i) => i.id === l.id)),
        ]);
        setOutputs(o);
        setMoreRaw(r.length === 100);
        setRawPageCount(r.length);
        setMoreOutput(o.length === 100);
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
  }, [onExpired, previous, attempt]);
  async function more(kind: "raw" | "prepared") {
    setMoreBusy(true);
    setLoadError("");
    try {
      const current = kind === "raw" ? raw : outputs;
      // Offset excludes recipe lines appended outside the loaded catalogue pages.
      const offset = kind === "raw" ? rawPageCount : outputs.length;
      const next = await productionApi.items(kind, offset);
      const merged = [
        ...current,
        ...next.filter((i) => !current.some((c) => c.id === i.id)),
      ];
      if (kind === "raw") {
        setRaw(merged);
        setRawPageCount(offset + next.length);
        setMoreRaw(next.length === 100);
      } else {
        setOutputs(merged);
        setMoreOutput(next.length === 100);
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else setLoadError(errorMessage(cause));
    } finally {
      setMoreBusy(false);
    }
  }
  function patch(key: string, value: Partial<(typeof lines)[number]>) {
    setLines((current) =>
      current.map((l) => (l.key === key ? { ...l, ...value } : l)),
    );
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const errors: Record<string, string> = {};
    if (!output) errors.output_item_id = s.required;
    if (wholeError(expected)) errors.expected_yield = t.wholeError;
    const sizeError = stockQuantityError(portion, portionUnit);
    if (sizeError) errors.portion_quantity = sizeError;
    if (!instructions.trim()) errors.instructions = s.required;
    for (const line of lines) {
      if (!line.item_id) errors[`${line.key}-item`] = s.required;
      const error = stockQuantityError(line.quantity, line.unit);
      if (error) errors[`${line.key}-quantity`] = error;
    }
    if (new Set(lines.map((l) => l.item_id)).size !== lines.length)
      errors.lines = t.duplicateIngredient;
    op.setFields(errors);
    op.setError(errors.lines || "");
    if (Object.keys(errors).length) {
      focusInvalid(form);
      return;
    }
    const body = {
      output_item_id: output,
      previous_version: previous?.version || 0,
      expected_yield: Number(expected),
      portion_quantity: decimalText(portion),
      portion_unit: portionUnit,
      instructions: instructions.trim(),
      lines: lines.map(({ item_id, quantity, unit }) => ({
        item_id,
        quantity: decimalText(quantity),
        unit,
      })),
    };
    if (await op.run(body, (key) => productionApi.createRecipe(body, key)))
      onSaved();
    else focusInvalid(form);
  }
  if (loading) return <LoadingState />;
  return (
    <form
      className="form-stack"
      onSubmit={(event) => void submit(event)}
      noValidate
    >
      {loadError && (
        <Alert>
          {loadError}
          <Button
            variant="secondary"
            onClick={() => {
              setLoading(true);
              setLoadError("");
              setAttempt((n) => n + 1);
            }}
          >
            {t.refresh}
          </Button>
        </Alert>
      )}
      <p className="field-hint">
        {previous
          ? `${s.version} ${previous.version} → ${previous.version + 1}`
          : t.versionNote}
      </p>
      <fieldset
        disabled={op.busy || moreBusy}
        className="form-stack plain-fieldset"
      >
        {previous ? (
          <h3>{previous.output_name}</h3>
        ) : (
          <Select
            label={t.output}
            value={output}
            onChange={(e) => setOutput(e.target.value)}
            error={op.fields.output_item_id}
            required
          >
            <option value="">{t.choose}</option>
            {outputs.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} · {s.units[i.unit]}
              </option>
            ))}
          </Select>
        )}
        {!previous && moreOutput && (
          <Button variant="secondary" onClick={() => void more("prepared")}>
            {t.moreItems}
          </Button>
        )}
        {!outputs.length && !previous && (
          <p className="field-hint">{t.setup}</p>
        )}
        <Input
          label={t.expected}
          hint={
            outputs.find((i) => i.id === output)?.unit === "pcs"
              ? s.units.pcs
              : previous?.output_unit === "pcs"
                ? s.units.pcs
                : s.units.portion
          }
          inputMode="numeric"
          maxLength={9}
          value={expected}
          onChange={(e) => setExpected(e.target.value)}
          error={op.fields.expected_yield}
          required
        />
        <div className="stock-form-grid">
          <Input
            label={t.portion}
            hint={t.portionHint}
            inputMode="decimal"
            maxLength={24}
            value={portion}
            onChange={(e) => setPortion(e.target.value)}
            error={op.fields.portion_quantity}
            required
          />
          <Select
            label={s.unit}
            value={portionUnit}
            onChange={(e) => setPortionUnit(e.target.value as RawUnit)}
          >
            {(["g", "kg", "ml", "l"] as const).map((u) => (
              <option key={u} value={u}>
                {s.units[u]}
              </option>
            ))}
          </Select>
        </div>
        <Input
          label={t.instructions}
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          error={op.fields.instructions}
          maxLength={2000}
          required
        />
        {lines.map((line, index) => (
          <fieldset className="production-ingredient" key={line.key}>
            <legend>
              {t.ingredient} {index + 1}
            </legend>
            <Select
              label={t.ingredient}
              value={line.item_id}
              onChange={(e) =>
                patch(line.key, {
                  item_id: e.target.value,
                  unit: (raw.find((i) => i.id === e.target.value)?.unit ||
                    "kg") as RawUnit,
                })
              }
              error={op.fields[`${line.key}-item`]}
              required
            >
              <option value="">{t.choose}</option>
              {raw.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </Select>
            <div className="stock-form-grid">
              <Input
                label={t.norm}
                inputMode="decimal"
                maxLength={24}
                value={line.quantity}
                onChange={(e) => patch(line.key, { quantity: e.target.value })}
                error={op.fields[`${line.key}-quantity`]}
                required
              />
              <Select
                label={s.unit}
                value={line.unit}
                onChange={(e) =>
                  patch(line.key, { unit: e.target.value as RawUnit })
                }
              >
                {rawUnits(line.unit).map((u) => (
                  <option key={u} value={u}>
                    {s.units[u]}
                  </option>
                ))}
              </Select>
            </div>
            {lines.length > 1 && (
              <Button
                variant="ghost"
                onClick={() =>
                  setLines((current) =>
                    current.filter((l) => l.key !== line.key),
                  )
                }
              >
                {t.removeIngredient} {index + 1}
              </Button>
            )}
          </fieldset>
        ))}
        {moreRaw && (
          <Button variant="secondary" onClick={() => void more("raw")}>
            {t.moreItems}
          </Button>
        )}
        <Button
          variant="secondary"
          disabled={lines.length >= 30}
          onClick={() =>
            setLines((current) => [
              ...current,
              {
                key: crypto.randomUUID(),
                item_id: "",
                quantity: "",
                unit: "kg",
              },
            ])
          }
        >
          {t.addIngredient}
        </Button>
      </fieldset>
      {op.error && <Alert>{op.error}</Alert>}
      <Button type="submit" loading={op.busy} disabled={moreBusy}>
        {t.saveRecipe}
      </Button>
    </form>
  );
}
