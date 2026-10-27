import { useRef, useState } from "react";
import { Input, type InputProps } from "./Input";

type NumericInputProps = Omit<
  InputProps,
  | "type"
  | "value"
  | "defaultValue"
  | "onChange"
  | "inputMode"
  | "onCompositionStart"
  | "onCompositionEnd"
> & {
  value: string;
  onValueChange: (value: string) => void;
  inputMode?: "numeric" | "decimal";
  allowNegative?: boolean;
};

export function NumericInput({
  value,
  onValueChange,
  inputMode = "decimal",
  allowNegative = false,
  ...props
}: NumericInputProps) {
  const composing = useRef(false);
  const [draft, setDraft] = useState<string | null>(null);
  function accept(next: string) {
    const unsigned = allowNegative ? next.replace(/^-/, "") : next;
    return inputMode === "numeric"
      ? /^\d*$/.test(unsigned)
      : /^\d*(?:[.,]\d*)?$/.test(unsigned);
  }
  return (
    <Input
      {...props}
      type="text"
      inputMode={inputMode}
      value={draft ?? value}
      onChange={(event) => {
        const next = event.target.value;
        if (composing.current) {
          setDraft(next);
        } else if (accept(next)) {
          onValueChange(next);
        }
      }}
      onCompositionStart={(event) => {
        composing.current = true;
        setDraft(event.currentTarget.value);
      }}
      onCompositionEnd={(event) => {
        composing.current = false;
        const next = event.currentTarget.value;
        setDraft(null);
        if (accept(next)) onValueChange(next);
      }}
    />
  );
}
