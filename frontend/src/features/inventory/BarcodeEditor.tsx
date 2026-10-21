import { useState } from "react";
import { request } from "../../shared/api/http";
import type { StockItem } from "../../shared/api/inventory";
import { useOperation } from "../../shared/lib/useOperation";
import { Dialog } from "../../shared/ui/Dialog";
import { Input } from "../../shared/ui/Input";
import { Button } from "../../shared/ui/Button";
import { Alert } from "../../shared/ui/Feedback";
export function BarcodeEditor({
  item,
  onClose,
  onSaved,
  onExpired,
}: {
  item: StockItem;
  onClose: () => void;
  onSaved: () => void;
  onExpired: () => void;
}) {
  const [value, setValue] = useState(item.barcode || "");
  const op = useOperation(onExpired);
  return (
    <Dialog
      open
      title={`Штрихкод: ${item.name}`}
      onClose={onClose}
      busy={op.busy}
    >
      <form
        className="form-stack"
        onSubmit={(e) => {
          e.preventDefault();
          const body = {
            barcode: value || null,
            expected_barcode: item.barcode || null,
          };
          void op
            .run(body, (key) =>
              request(`/inventory/items/${item.id}/barcode`, "PUT", body, {
                "Idempotency-Key": key,
              }),
            )
            .then((ok) => {
              if (ok) onSaved();
            });
        }}
      >
        <Input
          label="Штрихкод"
          hint="8–14 цифр. Пустое поле убирает штрихкод."
          inputMode="numeric"
          maxLength={14}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          error={op.fields.barcode}
        />
        {op.error && <Alert>{op.error}</Alert>}
        <Button type="submit" loading={op.busy}>
          Сохранить штрихкод
        </Button>
      </form>
    </Dialog>
  );
}
