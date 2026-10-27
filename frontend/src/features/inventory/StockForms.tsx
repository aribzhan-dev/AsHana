import { NumericInput } from "../../shared/ui/NumericInput";
import { CategorySelect } from "./CategorySelect";
import { PhotoField } from "./PhotoField";
import { useEffect, useState } from "react";
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
import { catalogApi } from "../../shared/api/catalog";

type Props = {
  onExpired: () => void;
  onSaved: () => void;
  onCreated?: (id: string, unit: string, purchasePrice: number) => void;
  receiving?: boolean;
  previous?: StockItem;
  onBusy?: (busy: boolean) => void;
};
export function ItemForm({
  onExpired,
  onSaved,
  onCreated,
  receiving = false,
  previous,
  onBusy,
}: Props) {
  const [barcode, setBarcode] = useState(previous?.barcode || "");
  const [category, setCategory] = useState(previous?.category || "");
  const [always, setAlways] = useState(previous?.always_on_menu ?? false);
  const [purchase, setPurchase] = useState(
    String((previous?.purchase_price_minor || 0) / 100),
  );
  const [sale, setSale] = useState(
    String((previous?.sale_price_minor || 0) / 100),
  );
  const [name, setName] = useState(previous?.name || ""),
    [kind, setKind] = useState<ItemInput["kind"]>(
      previous?.kind || "purchased",
    ),
    [unit, setUnit] = useState<ItemInput["unit"]>(previous?.unit || "pcs"),
    [notice, setNotice] = useState(false);
  const mutation = useStockMutation(onExpired);
  useEffect(() => onBusy?.(mutation.busy), [mutation.busy, onBusy]);
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
    const purchaseMinor = costMinor(purchase),
      saleMinor = costMinor(sale);
    if (purchaseMinor === undefined || saleMinor === undefined) {
      mutation.setFields({
        purchase_price_minor: purchaseMinor === undefined ? t.invalidCost : "",
        sale_price_minor: saleMinor === undefined ? t.invalidCost : "",
      });
      focusInvalid(event.currentTarget);
      return;
    }
    const data = {
      category: category.trim(),
      purchase_price_minor: purchaseMinor,
      sale_price_minor: saleMinor,
      name: name.trim(),
      kind,
      unit,
      barcode: kind === "purchased" ? barcode || null : null,
      always_on_menu: kind === "purchased" && always,
    };
    if (
      await mutation.run(data, async (key) => {
        const result = previous
          ? await inventoryApi.updateItem(
              previous.id,
              {
                name: data.name,
                barcode: data.barcode,
                category: data.category,
                purchase_price_minor: purchaseMinor,
                sale_price_minor: saleMinor,
                expected_version: previous.version ?? 1,
                always_on_menu: data.always_on_menu,
              },
              key,
            )
          : await inventoryApi.createItem(data, key);
        if (data.always_on_menu)
          // Without catalog.manage the goods join new periods when a manager creates them.
          await catalogApi
            .syncPermanent(crypto.randomUUID())
            .catch(() => undefined);
        onCreated?.(result.subject_id, unit, purchaseMinor);
      })
    ) {
      setName("");
      setBarcode("");
      setNotice(true);
      onSaved();
    }
  }
  return (
    <div className="form-stack">
      <form
        noValidate
        onSubmit={(event) => void submit(event)}
        aria-label={previous ? "Редактировать товар" : "Создать товар"}
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
            disabled={!!previous}
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
          <CategorySelect
            value={category}
            onChange={setCategory}
            error={mutation.fields.category}
          />
          <div className="stock-form-grid">
            <NumericInput
              label="Закупочная цена, ₸"
              inputMode="decimal"
              value={purchase}
              onValueChange={setPurchase}
              error={mutation.fields.purchase_price_minor}
            />
            <NumericInput
              label="Цена продажи, ₸"
              inputMode="decimal"
              value={sale}
              onValueChange={setSale}
              error={mutation.fields.sale_price_minor}
            />
          </div>
          {kind === "purchased" && (
            <NumericInput
              label="Штрихкод"
              placeholder="8–14 цифр, необязательно"
              inputMode="numeric"
              maxLength={14}
              value={barcode}
              onValueChange={setBarcode}
              error={mutation.fields.barcode}
            />
          )}
          {kind === "purchased" && (
            <label className="check-label switch-label">
              <input
                type="checkbox"
                checked={always}
                onChange={(e) => setAlways(e.target.checked)}
              />
              <span>
                Всегда в меню
                <small>
                  Показывать на сайте и в кассе, пока товар есть на складе
                </small>
              </span>
            </label>
          )}
          {previous && previous.kind !== "raw" && (
            <PhotoField item={previous} onChanged={() => undefined} />
          )}
          {mutation.fields.always_on_menu && (
            <p className="field-error">{mutation.fields.always_on_menu}</p>
          )}
          <Select
            label={t.unit}
            disabled={!!previous}
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
          {previous ? "Сохранить изменения" : "Создать товар"}
        </Button>
      </form>
    </div>
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
          <NumericInput
            label={t.quantity}
            value={values.quantity}
            onValueChange={(value) => set("quantity", value)}
            error={mutation.fields.quantity}
            inputMode={
              unit === "pcs" || unit === "portion" ? "numeric" : "decimal"
            }
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
          <NumericInput
            label={t.cost}
            value={values.cost}
            onValueChange={(value) => set("cost", value)}
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
