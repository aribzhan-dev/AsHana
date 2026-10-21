import type { ButtonHTMLAttributes } from "react";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  loading?: boolean;
  icon?: IconName;
};
export function Button({
  type = "button",
  variant = "primary",
  loading = false,
  disabled,
  icon,
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      type={type}
      className={`button button-${variant} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? (
        <span className="spinner" aria-hidden="true" />
      ) : icon ? (
        <Icon name={icon} />
      ) : null}
      {children}
    </button>
  );
}
export function IconButton({
  label,
  icon,
  ...props
}: Omit<ButtonProps, "children"> & { label: string; icon: IconName }) {
  return (
    <Button
      {...props}
      icon={icon}
      className={`icon-button ${props.className || ""}`}
      aria-label={label}
      title={label}
    />
  );
}
