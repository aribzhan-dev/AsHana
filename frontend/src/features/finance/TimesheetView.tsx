import { useState } from "react";
import {
  financeApi,
  type Accrual,
  type FinanceDetails,
  type Worker,
} from "../../shared/api/finance";
import {
  almatyInstant,
  almatyNow,
  stockDate,
} from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Dialog } from "../../shared/ui/Dialog";
import { Alert } from "../../shared/ui/Feedback";
import { Input, Select } from "../../shared/ui/Input";

export function TimesheetView({
  payroll,
  details,
  onChanged,
}: {
  payroll: Accrual[];
  details: FinanceDetails;
  onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const names = Object.fromEntries(
    payroll.map((a) => [a.worker.id, a.worker.name]),
  );
  const op = useOperation(() => window.location.reload());
  return (
    <div className="form-stack">
      <div className="button-row">
        <Button icon="plus" onClick={() => setAdding(true)}>
          Добавить смену
        </Button>
      </div>
      {op.error && <Alert>{op.error}</Alert>}
      {!details.shifts.length ? (
        <p className="muted">Смен за месяц нет.</p>
      ) : (
        <div className="table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                <th>Сотрудник</th>
                <th>Начало</th>
                <th>Конец</th>
                <th className="num">Часов</th>
                <th>Кто отметил</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {details.shifts.map((s) => (
                <tr key={s.id} className={s.voided ? "muted strike" : ""}>
                  <td>
                    {names[s.worker_id] ?? "Сотрудник"}
                    {s.note && <small className="muted">{s.note}</small>}
                  </td>
                  <td>{stockDate(s.starts_at)}</td>
                  <td>{s.ends_at ? stockDate(s.ends_at) : "идёт сейчас"}</td>
                  <td className="num">{s.hours.replace(".", ",")}</td>
                  <td>
                    {s.source === "self" ? "Сам сотрудник" : "Управляющий"}
                  </td>
                  <td>
                    {!s.voided && (
                      <Button
                        variant="ghost"
                        loading={op.busy}
                        onClick={() => {
                          const reason = window.prompt("Причина отмены смены");
                          if (!reason?.trim()) return;
                          void op
                            .run({ shift: s.id, reason }, (key) =>
                              financeApi.voidShift(s.id, reason.trim(), key),
                            )
                            .then((ok) => ok && onChanged());
                        }}
                      >
                        Отменить
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {adding && (
        <ShiftDialog
          workers={payroll.map((a) => a.worker)}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function ShiftDialog({
  workers,
  onClose,
  onSaved,
}: {
  workers: Worker[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const today = almatyNow().slice(0, 10);
  const [worker, setWorker] = useState(workers.find((w) => w.active)?.id ?? ""),
    [start, setStart] = useState(`${today}T08:00`),
    [end, setEnd] = useState(`${today}T17:00`),
    [note, setNote] = useState("");
  const op = useOperation(() => window.location.reload());
  async function save() {
    const s = almatyInstant(start),
      e = almatyInstant(end);
    if (!worker || !s || !e) {
      op.setError("Выберите сотрудника и время смены");
      return;
    }
    const body = { starts_at: s, ends_at: e, note };
    if (
      await op.run({ worker, ...body }, (key) =>
        financeApi.shift(worker, body, key),
      )
    )
      onSaved();
  }
  return (
    <Dialog open title="Смена в табель" busy={op.busy} onClose={onClose}>
      <form
        className="form-stack"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <Select
          label="Сотрудник"
          value={worker}
          onChange={(e) => setWorker(e.target.value)}
        >
          {workers.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </Select>
        <div className="stock-form-grid">
          <Input
            label="Начало (Астана)"
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
          <Input
            label="Конец (Астана)"
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            error={op.fields.ends_at}
          />
        </div>
        <Input
          label="Комментарий"
          maxLength={200}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {op.error && <Alert>{op.error}</Alert>}
        <Button type="submit" loading={op.busy}>
          Добавить
        </Button>
      </form>
    </Dialog>
  );
}
