import { useState } from "react";
import type { FormEvent } from "react";
import {
  inventoryApi,
  type StockItem,
  type ItemInput,
} from "../../shared/api/inventory";
import { Input, Select } from "../../shared/ui/Input";
import { Button } from "../../shared/ui/Button";
import { Alert, Card, EmptyState, Toast } from "../../shared/ui/Feedback";
import { inventoryRu as t } from "../../shared/locales/inventory";
import { focusInvalid } from "../../shared/lib/forms";
import {
  almatyInstant,
  almatyNow,
  costMinor,
  decimalText,
  stockQuantityError,
} from "../../shared/lib/inventory-validation";
import { useStockMutation } from "./useStockMutation";

type Props = {
  onExpired: () => void;
  onSaved: () => void;
  onCreated?: (id: string, unit: string) => void;
  receiving?: boolean;
};
export function ItemForm({
  onExpired,
  onSaved,
  onCreated,
  receiving = false,
}: Props) {
  const [barcode, setBarcode] = useState("");
  const [name, setName] = useState(""),
    [kind, setKind] = useState<ItemInput["kind"]>("raw"),
    [unit, setUnit] = useState<ItemInput["unit"]>("kg"),
    [notice, setNotice] = useState(false);
  const mutation = useStockMutation(onExpired);
  const units =
    kind === "raw"
      ? ["kg", "l"]
      : kind === "purchased"
        ? ["pcs"]
        : ["pcs", "portion"];
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(false);
    if (!name.trim()) {
      mutation.setFields({ name: t.required });
      focusInvalid(event.currentTarget);
      return;
    }
    const data = {
      name: name.trim(),
      kind,
      unit,
      barcode: kind === "purchased" ? barcode || null : null,
    };
    if (
      await mutation.run(data, async (key) => {
        const result = await inventoryApi.createItem(data, key);
        onCreated?.(result.subject_id, unit);
      })
    ) {
      setName("");
      setBarcode("");
      setNotice(true);
      onSaved();
    }
  }
  return (
    <Card>
      <h2>{t.createItem}</h2>
      <form
        noValidate
        onSubmit={(event) => void submit(event)}
        aria-label={t.createItem}
      >
        <fieldset disabled={mutation.busy} className="form-fields">
          <Input
            label={t.name}
            placeholder={t.namePlaceholder}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
            error={mutation.fields.name}
          />
          <Select
            label={t.kind}
            value={kind}
            onChange={(e) => {
              const next = e.target.value as ItemInput["kind"];
              setKind(next);
              setUnit(next === "raw" ? "kg" : "pcs");
            }}
          >
            {Object.entries(t.kinds)
              .filter(([code]) => !receiving || code !== "prepared")
              .map(([code, label]) => (
                <option value={code} key={code}>
                  {label}
                </option>
              ))}
          </Select>
          {kind === "purchased" && (
            <Input
              label="Штрихкод"
              placeholder="8–14 цифр, необязательно"
              inputMode="numeric"
              maxLength={14}
              value={barcode}
              onChange={(e) =>
                setBarcode(e.target.value.replace(/[^0-9]/g, ""))
              }
              error={mutation.fields.barcode}
            />
          )}
          <Select
            label={t.unit}
            value={unit}
            error={mutation.fields.unit}
            onChange={(e) => setUnit(e.target.value as ItemInput["unit"])}
          >
            {units.map((code) => (
              <option key={code} value={code}>
                {t.units[code as keyof typeof t.units]}
              </option>
            ))}
          </Select>
        </fieldset>
        {kind === "prepared" && <p className="field-hint">{t.preparedNote}</p>}
        {mutation.error && <Alert>{mutation.error}</Alert>}
        {notice && (
          <Toast onClose={() => setNotice(false)}>{t.itemSaved}</Toast>
        )}
        <Button type="submit" loading={mutation.busy} icon="plus">
          {t.createItem}
        </Button>
      </form>
    </Card>
  );
}

export function ReceiptForm({
  items,
  onExpired,
  onSaved,
}: Props & { items: StockItem[] }) {
  const [itemId, setItemId] = useState(""),
    [unit, setUnit] = useState("kg"),
    [notice, setNotice] = useState(false);
  const [values, setValues] = useState({
    label: "",
    quantity: "",
    cost: "",
    received: almatyNow(),
    expires: "",
    source: "",
  });
  const mutation = useStockMutation(onExpired),
    eligible = items.filter((item) => item.kind !== "prepared");
  const selected = eligible.find((item) => item.id === itemId);
  const units =
    selected?.unit === "kg"
      ? ["kg", "g"]
      : selected?.unit === "l"
        ? ["l", "ml"]
        : ["pcs"];
  const set = (field: keyof typeof values, value: string) =>
    setValues((previous) => ({ ...previous, [field]: value }));
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(false);
    const received = almatyInstant(values.received),
      expires = almatyInstant(values.expires),
      cost = costMinor(values.cost);
    const errors = {
      item_id: selected ? "" : t.required,
      label: values.label.trim() ? "" : t.required,
      quantity: stockQuantityError(values.quantity, unit) || "",
      total_cost_minor: cost === undefined ? t.invalidCost : "",
      received_at: received ? "" : t.invalidDate,
      expires_at: expires ? "" : t.invalidDate,
      source: values.source.trim() ? "" : t.required,
    };
    mutation.setFields(errors);
    mutation.setError("");
    if (
      Object.values(errors).some(Boolean) ||
      !received ||
      !expires ||
      cost === undefined
    ) {
      focusInvalid(event.currentTarget);
      return;
    }
    const data = {
      item_id: itemId,
      label: values.label.trim(),
      quantity: decimalText(values.quantity),
      unit: unit as "kg" | "g" | "l" | "ml" | "pcs",
      total_cost_minor: cost,
      received_at: received,
      expires_at: expires,
      source: values.source.trim(),
    };
    if (await mutation.run(data, (key) => inventoryApi.receive(data, key))) {
      setValues({
        label: "",
        quantity: "",
        cost: "",
        received: almatyNow(),
        expires: "",
        source: "",
      });
      setNotice(true);
      onSaved();
    }
  }
  if (!eligible.length) return <EmptyState title={t.noReceivable} />;
  return (
    <Card>
      <h2>{t.receive}</h2>
      <form aria-label={t.receive} noValidate onSubmit={(e) => void submit(e)}>
        <fieldset
          className="form-fields stock-form-grid"
          disabled={mutation.busy}
        >
          <Select
            label={t.item}
            value={itemId}
            error={mutation.fields.item_id}
            required
            onChange={(e) => {
              setItemId(e.target.value);
              setUnit(
                eligible.find((item) => item.id === e.target.value)?.unit ||
                  "kg",
              );
            }}
          >
            <option value="">{t.choose}</option>
            {eligible.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {t.units[item.unit]}
              </option>
            ))}
          </Select>
          <Input
            label={t.label}
            value={values.label}
            onChange={(e) => set("label", e.target.value)}
            error={mutation.fields.label}
            placeholder={t.labelPlaceholder}
            maxLength={100}
            required
          />
          <Input
            label={t.quantity}
            value={values.quantity}
            onChange={(e) => set("quantity", e.target.value)}
            error={mutation.fields.quantity}
            inputMode="decimal"
            placeholder="0"
            hint={t.quantityHint}
            maxLength={24}
            required
          />
          <Select
            label={t.unit}
            value={unit}
            error={mutation.fields.unit}
            onChange={(e) => setUnit(e.target.value)}
          >
            {units.map((code) => (
              <option key={code} value={code}>
                {t.units[code as keyof typeof t.units]}
              </option>
            ))}
          </Select>
          <Input
            label={t.cost}
            value={values.cost}
            onChange={(e) => set("cost", e.target.value)}
            error={mutation.fields.total_cost_minor}
            hint={t.costHint}
            inputMode="decimal"
            placeholder="0,00"
            maxLength={16}
            required
          />
          <Input
            label={t.source}
            value={values.source}
            onChange={(e) => set("source", e.target.value)}
            error={mutation.fields.source}
            placeholder={t.sourcePlaceholder}
            maxLength={200}
            required
          />
          <Input
            label={t.received}
            type="datetime-local"
            value={values.received}
            onChange={(e) => set("received", e.target.value)}
            error={mutation.fields.received_at}
            required
          />
          <Input
            label={t.expires}
            type="datetime-local"
            value={values.expires}
            onChange={(e) => set("expires", e.target.value)}
            error={mutation.fields.expires_at}
            hint={t.expiryHint}
            required
          />
        </fieldset>
        <p className="field-hint">{t.retryHint}</p>
        {mutation.error && <Alert>{mutation.error}</Alert>}
        {notice && (
          <Toast onClose={() => setNotice(false)}>{t.receiptSaved}</Toast>
        )}
        <Button type="submit" icon="plus" loading={mutation.busy}>
          {t.receive}
        </Button>
      </form>
    </Card>
  );
}
