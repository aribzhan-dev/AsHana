import { useState, type ReactNode } from "react";
import { IconButton } from "./Button";
import { Dialog } from "./Dialog";
export function DetailsButton({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <IconButton
        icon="eye"
        variant="secondary"
        label={`Подробнее: ${title}`}
        onClick={() => setOpen(true)}
      />
      {open && (
        <Dialog open title={title} onClose={() => setOpen(false)}>
          <div className="form-stack">{children}</div>
        </Dialog>
      )}
    </>
  );
}
