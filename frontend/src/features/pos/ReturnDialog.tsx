import { useEffect, useState } from "react";
import { posApi, type Sale } from "../../shared/api/pos";
import { errorMessage } from "../../shared/lib/forms";
import { stockMoney } from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Dialog } from "../../shared/ui/Dialog";
import { Alert, LoadingState } from "../../shared/ui/Feedback";
import { Input, Select } from "../../shared/ui/Input";
import { Stepper } from "../catalog/ProductSheet";

// Refund part of a counter sale: money goes back by the sale's method (test mode).
export function ReturnDialog({
  sale,
  onClose,
  onDone,
}: {
  sale: Sale;
  onClose: () => void;
  onDone: () => void;
}) {
  const [returned, setReturned] = useState<Record<string, number> | null>(null),
    [loadError, setLoadError] = useState(""),
    [picked, setPicked] = useState<Record<string, number>>({}),
    [reason, setReason] = useState(""),
    [disposition, setDisposition] = useState<"restock" | "write_off">(
      "restock",
    );
  const op = useOperation(() => window.location.reload());
  useEffect(() => {
    let active = true;
    posApi
      .returns(sale.id)
      .then((list) => {
        if (!active) return;
        const totals: Record<string, number> = {};
        for (const r of list)
          for (const l of r.lines)
            totals[l.entry_id] = (totals[l.entry_id] ?? 0) + l.quantity;
        setReturned(totals);
      })
      .catch((e) => {
        if (active) setLoadError(errorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [sale.id]);
  const amount = sale.lines.reduce(
    (sum, l) => sum + (picked[l.entry_id] ?? 0) * l.price_minor,
    0,
  );
  async function submit() {
    if (!amount) {
      op.setError("Выберите, что возвращают");
      return;
    }
    if (!reason.trim()) {
      op.setFields({ reason: "Укажите причину возврата" });
      return;
    }
    const body = {
      lines: Object.entries(picked)
        .filter(([, q]) => q > 0)
        .map(([entry_id, quantity]) => ({ entry_id, quantity })),
      reason: reason.trim(),
      disposition,
    };
    if (
      await op.run({ sale: sale.id, ...body }, (key) =>
        posApi.createReturn(sale.id, body, key),
      )
    )
      onDone();
  }
  return (
    <Dialog open title="Возврат по чеку" busy={op.busy} onClose={onClose}>
      {loadError ? (
        <Alert>{loadError}</Alert>
      ) : !returned ? (
        <LoadingState />
      ) : (
        <div className="form-stack">
          <div className="return-lines">
            {sale.lines.map((l) => {
              const left = l.quantity - (returned[l.entry_id] ?? 0);
              return (
                <div className="cutlery-line" key={l.entry_id}>
                  <span>
                    <strong>{l.name}</strong>
                    <small className="muted">
                      {stockMoney(l.price_minor)} · продано {l.quantity}
                      {left < l.quantity ? `, можно вернуть ${left}` : ""}
                    </small>
                  </span>
                  {left > 0 ? (
                    <Stepper
                      value={picked[l.entry_id] ?? 0}
                      min={0}
                      max={left}
                      label={`Вернуть: ${l.name}`}
                      onChange={(v) =>
                        setPicked({ ...picked, [l.entry_id]: v })
                      }
                    />
                  ) : (
                    <span className="muted">возвращено</span>
                  )}
                </div>
              );
            })}
          </div>
          <Select
            label="Что сделать с товаром"
            value={disposition}
            onChange={(e) =>
              setDisposition(e.target.value as "restock" | "write_off")
            }
          >
            <option value="restock">Вернуть в продажу (товар целый)</option>
            <option value="write_off">
              Не возвращать в продажу (испорчен)
            </option>
          </Select>
          <Input
            label="Причина"
            value={reason}
            maxLength={200}
            placeholder="Например, гость передумал"
            onChange={(e) => setReason(e.target.value)}
            error={op.fields.reason}
            required
          />
          {op.error && <Alert>{op.error}</Alert>}
          <Button loading={op.busy} onClick={() => void submit()}>
            Вернуть {stockMoney(amount)}
          </Button>
        </div>
      )}
    </Dialog>
  );
}
