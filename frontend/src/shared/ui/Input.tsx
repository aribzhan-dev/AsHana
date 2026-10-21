import { useId, useState } from "react";
import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";
import { uiRu as t } from "../locales/ui";
import { Icon, type IconName } from "./Icon";
import { IconButton } from "./Button";

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  hint?: string;
  leadingIcon?: IconName;
};
function FieldFrame({
  id,
  label,
  required,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className={`field ${error ? "field-invalid" : ""}`}>
      <label htmlFor={id}>
        {label}
        {required && <span className="required-mark" aria-hidden="true" />}
      </label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="field-hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="field-error">
          <Icon name="alert" />
          {error}
        </p>
      )}
    </div>
  );
}
export function Input({
  label,
  error,
  hint,
  type = "text",
  leadingIcon,
  id: providedId,
  ...props
}: InputProps) {
  const generated = useId();
  const id = providedId || generated;
  const [visible, setVisible] = useState(false);
  const described =
    [hint && `${id}-hint`, error && `${id}-error`, props["aria-describedby"]]
      .filter(Boolean)
      .join(" ") || undefined;
  return (
    <FieldFrame
      id={id}
      label={label}
      required={props.required}
      error={error}
      hint={hint}
    >
      <div
        className={`input-wrap ${leadingIcon ? "with-icon" : ""} ${type === "password" ? "with-action" : ""}`}
      >
        {leadingIcon && (
          <span className="input-icon">
            <Icon name={leadingIcon} />
          </span>
        )}
        <input
          {...props}
          id={id}
          type={type === "password" && visible ? "text" : type}
          aria-invalid={!!error}
          aria-describedby={described}
        />
        {type === "password" && (
          <IconButton
            className="input-action"
            variant="ghost"
            icon={visible ? "eye-off" : "eye"}
            label={visible ? t.hidePassword : t.showPassword}
            aria-pressed={visible}
            disabled={props.disabled}
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => setVisible(!visible)}
          />
        )}
      </div>
    </FieldFrame>
  );
}
export function PasswordInput(props: Omit<InputProps, "type">) {
  return <Input {...props} type="password" leadingIcon="lock" />;
}
export function PhoneInput({
  value,
  onChange,
  ...props
}: Omit<InputProps, "type">) {
  const [invalid, setInvalid] = useState(false);
  const digits = String(value || "").replace(/^\+7/, "");
  return (
    <div className="phone-field">
      <span className="phone-prefix" aria-hidden="true">
        +7
      </span>
      <Input
        {...props}
        value={digits}
        placeholder="700 000 00 00"
        autoComplete="tel-national"
        type="tel"
        inputMode="numeric"
        maxLength={32}
        error={invalid ? "Введите только 10 цифр после +7" : props.error}
        onChange={(event) => {
          let next = event.target.value;
          if (!/^[+0-9 ()-]*$/.test(next)) {
            setInvalid(true);
            return;
          }
          next = next.replace(/[ ()-]/g, "");
          if (next.startsWith("+7")) next = next.slice(2);
          else if (next.length === 11 && next.startsWith("7"))
            next = next.slice(1);
          if (!/^\d{0,10}$/.test(next)) {
            setInvalid(true);
            return;
          }
          setInvalid(false);
          event.target.value = next ? `+7${next}` : "";
          onChange?.(event);
        }}
      />
    </div>
  );
}
export function Select({
  label,
  error,
  hint,
  children,
  id: providedId,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  error?: string;
  hint?: string;
}) {
  const generated = useId();
  const id = providedId || generated;
  return (
    <FieldFrame
      id={id}
      label={label}
      required={props.required}
      error={error}
      hint={hint}
    >
      <select
        {...props}
        id={id}
        aria-invalid={!!error}
        aria-describedby={
          [
            hint && `${id}-hint`,
            error && `${id}-error`,
            props["aria-describedby"],
          ]
            .filter(Boolean)
            .join(" ") || undefined
        }
      >
        {children}
      </select>
    </FieldFrame>
  );
}
