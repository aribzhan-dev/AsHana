import { useState } from "react";
import { financeApi, type Accrual } from "../../shared/api/finance";
import type { Directory } from "../../shared/api/receiving";
import {
  almatyInstant,
  almatyNow,
  costMinor,
  shortMoney,
} from "../../shared/lib/inventory-validation";
import { kinds } from "./payment-kinds";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Dialog } from "../../shared/ui/Dialog";
import { Alert } from "../../shared/ui/Feedback";
import { Input, Select } from "../../shared/ui/Input";

export function PayDialog({
  accrual,
  month,
  methods,
  onClose,
  onSaved,
}: {
  accrual: Accrual;
  month: string;
  methods: Directory[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [kind, setKind] = useState<keyof typeof kinds>(
      accrual.paid ? "salary" : "advance",
    ),
    [sum, setSum] = useState(
      accrual.balance > 0 ? String(accrual.balance / 100) : "",
    ),
    [method, setMethod] = useState(methods[0]?.id ?? ""),
    [at, setAt] = useState(almatyNow()),
    [note, setNote] = useState("");
  const op = useOperation(() => window.location.reload());
  async function save() {
    const minor = costMinor(sum),
      time = almatyInstant(at);
    if (!minor) {
      op.setFields({ amount_minor: "Введите сумму" });
      return;
    }
    if (!time || !method) {
      op.setError("Выберите способ и дату выплаты");
      return;
    }
    const body = {
      month: `${month}-01`,
      kind,
      amount_minor: minor,
      payment_method_id: method,
      paid_at: time,
      note,
    };

    if (
      await op.run({ worker: accrual.worker.id, ...body }, (key) =>
        financeApi.pay(accrual.worker.id, body, key),
      )
    )
      onSaved();
  }
  return (
    <Dialog
      open
      title={`Выплата · ${accrual.worker.name}`}
      busy={op.busy}
      onClose={onClose}
    >
      <form
        className="form-stack"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <p>
          Начислено {shortMoney(accrual.total)}, выплачено{" "}
          {shortMoney(accrual.paid)}, долг{" "}
          <strong>{shortMoney(accrual.balance)}</strong>
        </p>
        <Select
          label="Вид выплаты"
          value={kind}
          onChange={(e) => setKind(e.target.value as keyof typeof kinds)}
        >
          {Object.entries(kinds).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </Select>
        <Input
          label="Сумма, ₸"
          inputMode="decimal"
          value={sum}
          onChange={(e) => setSum(e.target.value)}
          error={op.fields.amount_minor}
        />
        <Select
          label="Способ"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
        >
          {methods.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </Select>
        <Input
          label="Дата (Астана)"
          type="datetime-local"
          value={at}
          onChange={(e) => setAt(e.target.value)}
          error={op.fields.paid_at}
        />
        <Input
          label="Комментарий"
          maxLength={200}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {op.error && <Alert>{op.error}</Alert>}
        <Button type="submit" loading={op.busy}>
          Выплатить
        </Button>
      </form>
    </Dialog>
  );
}
