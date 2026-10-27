import { NumericInput } from "./NumericInput";
import type { InputProps } from "./Input";
import { IconButton } from "./Button";
import { uiRu as t } from "../locales/ui";

import { quantityError } from "../lib/quantity";

export function QuantityInput({
  value,
  onValueChange,
  min = 1,
  max = 9999,
  ...props
}: Omit<InputProps, "value" | "onChange" | "type" | "min" | "max"> & {
  value: string;
  onValueChange: (value: string) => void;
  min?: number;
  max?: number;
}) {
  function step(delta: number) {
    const current = quantityError(value, min, max) ? min : Number(value);
    onValueChange(String(Math.max(min, Math.min(max, current + delta))));
  }
  return (
    <div className="quantity-control">
      <NumericInput
        {...props}
        value={value}
        inputMode="numeric"
        onValueChange={onValueChange}
      />
      <div className="quantity-actions">
        <IconButton
          variant="secondary"
          label={t.decrease}
          icon="minus"
          disabled={props.disabled || Number(value) <= min}
          onClick={() => step(-1)}
        />
        <IconButton
          variant="secondary"
          label={t.increase}
          icon="plus"
          disabled={props.disabled || Number(value) >= max}
          onClick={() => step(1)}
        />
      </div>
    </div>
  );
}
