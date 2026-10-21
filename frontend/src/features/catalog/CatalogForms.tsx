import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../../shared/api/http";
import {
  catalogApi,
  type Period,
  type MenuEntry,
} from "../../shared/api/catalog";
import type { StockItem } from "../../shared/api/inventory";
import { errorMessage, focusInvalid } from "../../shared/lib/forms";
import {
  almatyInstant,
  costMinor,
} from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { catalogRu as t } from "../../shared/locales/catalog";
import { inventoryRu as s } from "../../shared/locales/inventory";
import { Button } from "../../shared/ui/Button";
import { Alert, LoadingState } from "../../shared/ui/Feedback";
import { Input, Select } from "../../shared/ui/Input";

const localInstant = (value: string) =>
  new Date(Date.parse(value) + 5 * 3600000).toISOString().slice(0, 16);
type Callbacks = {
  onSaved: () => void;
  onExpired: () => void;
  onBusy: (busy: boolean) => void;
};
export function PeriodForm({
  previous,
  day,
  onSaved,
  onExpired,
  onBusy,
}: { previous?: Period; day: string } & Callbacks) {
  const op = useOperation(onExpired);
  useEffect(() => {
    onBusy(op.busy);
  }, [onBusy, op.busy]);
  const [name, setName] = useState(previous?.name || ""),
    [starts, setStarts] = useState(
      previous ? localInstant(previous.starts_at) : "",
    ),
    [ends, setEnds] = useState(previous ? localInstant(previous.ends_at) : ""),
    [published, setPublished] = useState(previous?.published || false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields: Record<string, string> = {};
    const start = almatyInstant(starts),
      end = almatyInstant(ends);
    if (!name.trim()) fields.name = s.required;
    if (!start) fields.starts_at = s.invalidDate;
    if (
      !end ||
      (start &&
        (Date.parse(end) <= Date.parse(start) ||
          Date.parse(end) - Date.parse(start) > 86400000))
    )
      fields.ends_at = t.invalidPeriod;
    op.setFields(fields);
    if (Object.keys(fields).length || !start || !end) {
      focusInvalid(form);
      return;
    }
    const body = {
      name: name.trim(),
      starts_at: start,
      ends_at: end,
      published,
      expected_version: previous?.version || 0,
    };
    if (
      await op.run(body, (key) =>
        catalogApi.savePeriod(previous?.id, body, key),
      )
    )
      onSaved();
    else focusInvalid(form);
  }
  return (
    <form className="form-stack" onSubmit={(e) => void submit(e)} noValidate>
      <fieldset className="plain-fieldset form-stack" disabled={op.busy}>
        <Input
          label={t.name}
          placeholder={t.nameHint}
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={op.fields.name}
          maxLength={100}
          required
        />
        <p className="field-hint">
          {t.day}: {day}
        </p>
        <Input
          label={t.starts}
          type="datetime-local"
          value={starts}
          onChange={(e) => setStarts(e.target.value)}
          error={op.fields.starts_at}
          required
        />
        <Input
          label={t.ends}
          hint={t.windowHint}
          type="datetime-local"
          value={ends}
          onChange={(e) => setEnds(e.target.value)}
          error={op.fields.ends_at}
          required
        />
        <label className="production-confirm">
          <input
            type="checkbox"
            checked={published}
            onChange={(e) => setPublished(e.target.checked)}
          />
          <span>{t.publishPeriod}</span>
        </label>
      </fieldset>
      {op.error && <Alert>{op.error}</Alert>}
      <Button type="submit" loading={op.busy}>
        {t.savePeriod}
      </Button>
    </form>
  );
}
export function EntryForm({
  period,
  previous,
  onSaved,
  onExpired,
  onBusy,
}: { period: Period; previous?: MenuEntry } & Callbacks) {
  const op = useOperation(onExpired);
  useEffect(() => {
    onBusy(op.busy);
  }, [onBusy, op.busy]);
  const [kind, setKind] = useState<"prepared" | "purchased">("prepared"),
    [items, setItems] = useState<StockItem[]>([]),
    [more, setMore] = useState(false),
    [loading, setLoading] = useState(!previous),
    [loadError, setLoadError] = useState(""),
    [attempt, setAttempt] = useState(0);
  const [itemId, setItemId] = useState(previous?.item_id || ""),
    [category, setCategory] = useState(previous?.category || ""),
    [description, setDescription] = useState(previous?.description || ""),
    [portion, setPortion] = useState(previous?.portion_label || ""),
    [price, setPrice] = useState(
      previous
        ? `${Math.floor(previous.price_minor / 100)}.${String(previous.price_minor % 100).padStart(2, "0")}`
        : "",
    ),
    [published, setPublished] = useState(previous?.published || false);
  useEffect(() => {
    if (previous) return;
    let active = true;
    void catalogApi
      .items(kind)
      .then((data) => {
        if (active) {
          setItems(data);
          setMore(data.length === 100);
        }
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
  }, [kind, previous, attempt, onExpired]);
  async function moreItems() {
    setLoading(true);
    setLoadError("");
    try {
      const next = await catalogApi.items(kind, items.length);
      setItems((current) => [...current, ...next]);
      setMore(next.length === 100);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else setLoadError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields: Record<string, string> = {};
    const minor = costMinor(price);
    if (!itemId) fields.item_id = s.required;
    if (!portion.trim()) fields.portion_label = s.required;
    if (minor === undefined) fields.price_minor = s.invalidCost;
    op.setFields(fields);
    if (Object.keys(fields).length || minor === undefined) {
      focusInvalid(form);
      return;
    }
    const body = {
      item_id: itemId,
      description: description.trim(),
      category: category.trim(),
      portion_label: portion.trim(),
      price_minor: minor,
      published,
      expected_version: previous?.version || 0,
    };
    if (
      await op.run(body, (key) =>
        catalogApi.saveEntry(period.id, previous?.id, body, key),
      )
    )
      onSaved();
    else focusInvalid(form);
  }
  return (
    <form className="form-stack" onSubmit={(e) => void submit(e)} noValidate>
      <p className="field-hint">{period.name}</p>
      {loadError && (
        <Alert>
          {loadError}
          <Button
            variant="secondary"
            onClick={() => {
              setLoadError("");
              setLoading(true);
              setAttempt((n) => n + 1);
            }}
          >
            {t.refresh}
          </Button>
        </Alert>
      )}
      <fieldset className="plain-fieldset form-stack" disabled={op.busy}>
        {previous ? (
          <h3>{previous.name}</h3>
        ) : (
          <>
            <Select
              label={t.kind}
              value={kind}
              disabled={loading}
              onChange={(e) => {
                setKind(e.target.value as typeof kind);
                setItemId("");
                setItems([]);
                setLoading(true);
                setLoadError("");
              }}
            >
              <option value="prepared">{s.kinds.prepared}</option>
              <option value="purchased">{s.kinds.purchased}</option>
            </Select>
            {loading && <LoadingState />}
            <Select
              label={t.item}
              value={itemId}
              disabled={loading}
              onChange={(e) => {
                setItemId(e.target.value);
                const selected = items.find((i) => i.id === e.target.value);
                setCategory(selected?.category || "");
                setPrice(String((selected?.sale_price_minor || 0) / 100));
              }}
              error={op.fields.item_id}
              required
            >
              <option value="">{t.choose}</option>
              {items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </Select>
            {!loading && !items.length && (
              <p className="field-hint">{t.stockHint}</p>
            )}
            {more && (
              <Button
                variant="secondary"
                loading={loading}
                onClick={() => void moreItems()}
              >
                {t.more}
              </Button>
            )}
          </>
        )}
        <Input
          label="Категория"
          list="menu-categories"
          placeholder="Например, Горячее, Супы, Напитки"
          value={category}
          maxLength={60}
          onChange={(e) => setCategory(e.target.value)}
          error={op.fields.category}
          hint="Выберите название из подсказки или введите новую категорию."
        />
        <datalist id="menu-categories">
          {[
            "Горячее",
            "Супы",
            "Салаты",
            "Гарниры",
            "Выпечка",
            "Напитки",
            "Молочные продукты",
          ].map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <Input
          label={t.portion}
          hint={t.portionHint}
          value={portion}
          onChange={(e) => setPortion(e.target.value)}
          maxLength={100}
          error={op.fields.portion_label}
          required
        />
        <Input
          label={t.description}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={1000}
          error={op.fields.description}
        />
        <Input
          label={t.price}
          hint={t.priceHint}
          inputMode="decimal"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          maxLength={24}
          error={op.fields.price_minor}
          required
        />
        <label className="production-confirm">
          <input
            type="checkbox"
            checked={published}
            onChange={(e) => setPublished(e.target.checked)}
          />
          <span>{t.publishEntry}</span>
        </label>
      </fieldset>
      <p className="field-hint">{t.publicationHint}</p>
      {op.error && <Alert>{op.error}</Alert>}
      <Button type="submit" loading={op.busy} disabled={loading || !!loadError}>
        {t.saveEntry}
      </Button>
    </form>
  );
}
