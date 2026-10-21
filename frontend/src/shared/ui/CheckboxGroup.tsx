import { useId } from "react";

export function CheckboxGroup<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled,
  error,
  hint,
}: {
  label: string;
  value: T[];
  options: { value: T; label: string; description?: string }[];
  onChange: (value: T[]) => void;
  disabled?: boolean;
  error?: string;
  hint?: string;
}) {
  const id = useId();
  return (
    <fieldset
      disabled={disabled}
      className="checkbox-group"
      aria-describedby={error ? id : undefined}
      aria-invalid={!!error}
    >
      <legend>{label}</legend>
      <div className="role-grid">
        {options.map((option) => (
          <label key={option.value} className="check-label">
            <input
              type="checkbox"
              aria-label={option.label}
              checked={value.includes(option.value)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...value, option.value]
                    : value.filter((item) => item !== option.value),
                )
              }
            />
            <span>
              {option.label}
              {option.description && <small>{option.description}</small>}
            </span>
          </label>
        ))}
      </div>
      {hint && <p className="field-hint">{hint}</p>}
      {error && (
        <p id={id} className="field-error">
          {error}
        </p>
      )}
    </fieldset>
  );
}
