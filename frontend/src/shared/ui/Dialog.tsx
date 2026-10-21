import { useEffect, useId, useRef } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { IconButton } from "./Button";
import { uiRu as t } from "../locales/ui";

export function Dialog({
  open,
  title,
  description,
  onClose,
  children,
  busy = false,
  className = "",
}: {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  busy?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || !open) return;
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    dialog.showModal();
    return () => {
      dialog.close();
      if (previous?.isConnected) {
        if (!previous.matches(":disabled")) previous.focus();
        else
          previous
            .closest("section")
            ?.querySelector<HTMLElement>(
              "input:not(:disabled), button:not(:disabled)",
            )
            ?.focus();
      }
    };
  }, [open]);
  function containTab(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Tab") return;
    const controls = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((element) => element.getClientRects().length > 0);
    const first = controls[0];
    const last = controls.at(-1);
    if (!first || !last) {
      event.preventDefault();
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
  return (
    <dialog
      ref={ref}
      className={`dialog ${className}`}
      onKeyDown={containTab}
      aria-labelledby={`${id}-title`}
      aria-describedby={description ? `${id}-description` : undefined}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="dialog-header">
        <h2 id={`${id}-title`}>{title}</h2>
        <IconButton
          variant="ghost"
          icon="close"
          label={t.close}
          onClick={onClose}
          disabled={busy}
        />
      </div>
      {description && (
        <p id={`${id}-description`} className="muted">
          {description}
        </p>
      )}
      {children}
    </dialog>
  );
}
