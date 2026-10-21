import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { Button, IconButton } from "./Button";
import { Icon } from "./Icon";
import { uiRu as t } from "../locales/ui";

export function Alert({
  children,
  title = t.errorTitle,
}: {
  children: ReactNode;
  title?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [children]);
  return (
    <div ref={ref} className="alert" role="alert" tabIndex={-1}>
      <Icon name="alert" />
      <div>
        <strong>{title}</strong>
        <div>{children}</div>
      </div>
    </div>
  );
}
export function Toast({
  children,
  onClose,
}: {
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="toast" role="status">
      <Icon name="check" />
      <span>{children}</span>
      <IconButton
        variant="ghost"
        icon="close"
        label={t.close}
        onClick={onClose}
      />
    </div>
  );
}
export function LoadingState({ label = t.loading }: { label?: string }) {
  return (
    <div className="empty-state" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}
export function EmptyState({
  title = t.empty,
  children,
}: {
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <Icon name="clock" />
      <strong>{title}</strong>
      {children}
    </div>
  );
}
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Alert>
      <p>{message}</p>
      <Button variant="secondary" onClick={onRetry}>
        {t.retry}
      </Button>
    </Alert>
  );
}
export function Card({
  children,
  className = "",
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  return (
    <section {...props} className={`card ${className}`}>
      {children}
    </section>
  );
}
export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
}
