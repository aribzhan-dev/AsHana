import { ProductImage } from "../../shared/ui/ProductImage";
import { useState } from "react";
import type { PublicEntry } from "../../shared/api/catalog";
import { shortMoney } from "../../shared/lib/inventory-validation";
import { yieldLabel } from "../../shared/lib/production-validation";
import { Button, IconButton } from "../../shared/ui/Button";
import { Dialog } from "../../shared/ui/Dialog";

export function Stepper({
  value,
  min = 1,
  max,
  label,
  onChange,
}: {
  value: number;
  min?: number;
  max: number;
  label: string;
  onChange: (value: number) => void;
}) {
  return (
    <div className="stepper" role="group" aria-label={label}>
      <IconButton
        variant="ghost"
        icon="minus"
        label="Уменьшить количество"
        disabled={value <= min}
        onClick={() => onChange(value - 1)}
      />
      <output aria-live="polite">{value}</output>
      <IconButton
        variant="ghost"
        icon="plus"
        label="Увеличить количество"
        disabled={value >= max}
        onClick={() => onChange(value + 1)}
      />
    </div>
  );
}

export function ProductSheet({
  entry,
  onAdd,
  onClose,
}: {
  entry: PublicEntry;
  onAdd: (quantity: number) => void;
  onClose: () => void;
}) {
  const [quantity, setQuantity] = useState(1);
  const max = Math.max(1, Math.min(10, entry.available));
  return (
    <Dialog open title={entry.name} className="product-sheet" onClose={onClose}>
      <ProductImage
        src={entry.image_url}
        category={entry.category}
        name={entry.name}
        className="product-sheet-art"
      />
      <p className="product-sheet-category">
        {entry.category || entry.period_name}
      </p>
      {entry.description && <p>{entry.description}</p>}
      <div className="product-sheet-price">
        <strong>{shortMoney(entry.price_minor)}</strong>
        <span className="muted">{entry.portion_label}</span>
      </div>
      <p className="stock-pill">
        <span aria-hidden="true" />В наличии:{" "}
        {yieldLabel(entry.available, entry.unit)}
      </p>
      <Stepper
        value={quantity}
        max={max}
        label={`Количество: ${entry.name}`}
        onChange={setQuantity}
      />
      <Button className="full-width" onClick={() => onAdd(quantity)}>
        Добавить в заказ · {shortMoney(entry.price_minor * quantity)}
      </Button>
    </Dialog>
  );
}
