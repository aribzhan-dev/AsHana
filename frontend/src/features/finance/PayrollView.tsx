import { useState } from "react";
import {
  basisPoints,
  financeApi,
  percent,
  type Accrual,
  type FinanceDetails,
  type Worker,
} from "../../shared/api/finance";
import type { Directory } from "../../shared/api/receiving";
import {
  almatyInstant,
  almatyNow,
  costMinor,
  shortMoney,
  stockDate,
} from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Dialog } from "../../shared/ui/Dialog";
import { Alert } from "../../shared/ui/Feedback";
import { Input, Select } from "../../shared/ui/Input";

const kinds = {
  advance: "Аванс",
  salary: "Зарплата",
  bonus: "Премия",
} as const;

function scheme(w: Worker): string {
  const parts = [];
  if (w.monthly_minor) parts.push(`оклад ${shortMoney(w.monthly_minor)}`);
  if (w.daily_minor) parts.push(`${shortMoney(w.daily_minor)} в день`);
  if (w.hourly_minor) parts.push(`${shortMoney(w.hourly_minor)} в час`);
  if (w.sales_bp)
    parts.push(
      `${percent(w.sales_bp)} от ${w.sales_base === "personal" ? "своих продаж" : "продаж столовой"}`,
    );
  if (w.profit_bp)
    parts.push(
      `${percent(w.profit_bp)} от ${w.profit_base === "simple" ? "упрощённой" : "полной"} прибыли`,
    );
  return parts.join(" + ") || "схема не задана";
}

export function PayrollView({
  month,
  payroll,
  details,
  methods,
  onChanged,
}: {
  month: string;
  payroll: Accrual[];
  details: FinanceDetails;
  methods: Directory[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<Worker | "new" | null>(null),
    [paying, setPaying] = useState<Accrual | null>(null);
  const total = payroll.reduce((n, a) => n + a.total, 0),
    paid = payroll.reduce((n, a) => n + a.paid, 0);
  return (
    <div className="form-stack">
      <div className="kpi-grid">
        <div className="kpi">
          <span>Начислено за месяц</span>
          <strong>{shortMoney(total)}</strong>
        </div>
        <div className="kpi">
          <span>Выплачено</span>
          <strong>{shortMoney(paid)}</strong>
        </div>
        <div className="kpi">
          <span>Осталось выплатить</span>
          <strong className={total - paid > 0 ? "debt" : ""}>
            {shortMoney(total - paid)}
          </strong>
        </div>
      </div>
      <div className="button-row">
        <Button icon="plus" onClick={() => setEditing("new")}>
          Добавить сотрудника
        </Button>
      </div>
      <div className="table-wrap">
        <table className="report-table payroll-table">
          <thead>
            <tr>
              <th>Сотрудник</th>
              <th className="num">Дней / часов</th>
              <th className="num">Оклад, дни, часы</th>
              <th className="num">% от продаж</th>
              <th className="num">% от прибыли</th>
              <th className="num">Начислено</th>
              <th className="num">Выплачено</th>
              <th className="num">Долг</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {payroll.map((a) => (
              <tr key={a.worker.id} className={a.worker.active ? "" : "muted"}>
                <td>
                  {a.worker.name}
                  <small className="muted">
                    {[a.worker.position, scheme(a.worker)]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </td>
                <td className="num">
                  {a.days} / {a.hours.replace(".", ",")}
                </td>
                <td className="num">
                  {shortMoney(a.monthly + a.daily + a.hourly)}
                </td>
                <td className="num">{shortMoney(a.sales)}</td>
                <td className="num">{shortMoney(a.profit)}</td>
                <td className="num">
                  <strong>{shortMoney(a.total)}</strong>
                </td>
                <td className="num">{shortMoney(a.paid)}</td>
                <td className={`num ${a.balance > 0 ? "debt" : ""}`}>
                  {shortMoney(a.balance)}
                </td>
                <td className="row-actions">
                  <Button variant="secondary" onClick={() => setPaying(a)}>
                    Выплатить
                  </Button>
                  <Button variant="ghost" onClick={() => setEditing(a.worker)}>
                    Изменить
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!payroll.length && (
        <p className="muted">
          Добавьте сотрудников: оклад, оплата за день или час, процент от продаж
          или прибыли — в любом сочетании.
        </p>
      )}
      <h3>Выплаты за месяц</h3>
      <MoneyList
        rows={details.payments.map((p) => ({
          ...p,
          label: `${p.subject_name} · ${kinds[p.kind as keyof typeof kinds] ?? p.kind}`,
        }))}
      />
      {editing && (
        <WorkerDialog
          worker={editing === "new" ? null : editing}
          staff={details.staff}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
      {paying && (
        <PayDialog
          accrual={paying}
          month={month}
          methods={methods}
          onClose={() => setPaying(null)}
          onSaved={() => {
            setPaying(null);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

export function MoneyList({
  rows,
}: {
  rows: {
    id: string;
    label: string;
    amount_minor: number;
    at: string;
    method_name: string;
    note: string;
  }[];
}) {
  if (!rows.length) return <p className="muted">Записей пока нет.</p>;
  return (
    <div className="table-wrap">
      <table className="report-table">
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                {r.label}
                {r.note && <small className="muted">{r.note}</small>}
              </td>
              <td>{stockDate(r.at)}</td>
              <td>{r.method_name}</td>
              <td className={`num ${r.amount_minor < 0 ? "debt" : ""}`}>
                {shortMoney(r.amount_minor)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WorkerDialog({
  worker,
  staff,
  onClose,
  onSaved,
}: {
  worker: Worker | null;
  staff: Record<string, string>[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const money = (v?: number) => (v ? String(v / 100) : "");
  const pct = (v?: number) => (v ? String(v / 100) : "");
  const [form, setForm] = useState({
    name: worker?.name ?? "",
    position: worker?.position ?? "",
    user_id: worker?.user_id ?? "",
    active: worker?.active ?? true,
    monthly: money(worker?.monthly_minor),
    daily: money(worker?.daily_minor),
    hourly: money(worker?.hourly_minor),
    sales: pct(worker?.sales_bp),
    sales_base: worker?.sales_base ?? "all",
    profit: pct(worker?.profit_bp),
    profit_base: worker?.profit_base ?? "full",
  });
  const op = useOperation(() => window.location.reload());
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });
  async function save() {
    const amounts = [form.monthly, form.daily, form.hourly].map((v) =>
      v.trim() ? costMinor(v) : 0,
    );
    const shares = [form.sales, form.profit].map(basisPoints);
    const fields: Record<string, string> = {};
    if (!form.name.trim()) fields.name = "Укажите имя";
    ["monthly_minor", "daily_minor", "hourly_minor"].forEach((key, i) => {
      if (amounts[i] === undefined) fields[key] = "Введите сумму в тенге";
    });
    if (shares[0] === undefined) fields.sales_bp = "Процент от 0 до 100";
    if (shares[1] === undefined) fields.profit_bp = "Процент от 0 до 100";
    if (Object.keys(fields).length) {
      op.setFields(fields);
      return;
    }
    const body = {
      name: form.name.trim(),
      position: form.position.trim(),
      user_id: form.user_id || null,
      active: form.active,
      monthly_minor: amounts[0]!,
      daily_minor: amounts[1]!,
      hourly_minor: amounts[2]!,
      sales_bp: shares[0]!,
      sales_base: form.sales_base,
      profit_bp: shares[1]!,
      profit_base: form.profit_base,
      expected_version: worker?.version ?? 0,
    };
    if (
      await op.run({ id: worker?.id, ...body }, (key) =>
        financeApi.worker(worker?.id ?? null, body, key),
      )
    )
      onSaved();
  }
  return (
    <Dialog
      open
      title={worker ? "Сотрудник и схема оплаты" : "Новый сотрудник"}
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
        <Input
          label="Имя"
          value={form.name}
          onChange={(e) => set({ name: e.target.value })}
          error={op.fields.name}
          required
        />
        <Input
          label="Должность"
          placeholder="Например, посудомойщица"
          value={form.position}
          onChange={(e) => set({ position: e.target.value })}
        />
        <Select
          label="Аккаунт в системе"
          value={form.user_id}
          onChange={(e) => set({ user_id: e.target.value })}
          error={op.fields.user_id}
          hint="Нужен для своих продаж и отметки смены. Можно без аккаунта."
        >
          <option value="">Без аккаунта</option>
          {staff.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({s.login})
            </option>
          ))}
        </Select>
        <div className="stock-form-grid">
          <Input
            label="Оклад в месяц, ₸"
            inputMode="decimal"
            value={form.monthly}
            onChange={(e) => set({ monthly: e.target.value })}
            error={op.fields.monthly_minor}
          />
          <Input
            label="За рабочий день, ₸"
            inputMode="decimal"
            value={form.daily}
            onChange={(e) => set({ daily: e.target.value })}
            error={op.fields.daily_minor}
          />
          <Input
            label="За час, ₸"
            inputMode="decimal"
            value={form.hourly}
            onChange={(e) => set({ hourly: e.target.value })}
            error={op.fields.hourly_minor}
          />
        </div>
        <div className="stock-form-grid">
          <Input
            label="% от продаж"
            inputMode="decimal"
            value={form.sales}
            onChange={(e) => set({ sales: e.target.value })}
            error={op.fields.sales_bp}
          />
          <Select
            label="От каких продаж"
            value={form.sales_base}
            onChange={(e) =>
              set({ sales_base: e.target.value as "all" | "personal" })
            }
          >
            <option value="all">Все продажи столовой</option>
            <option value="personal">Свои продажи на кассе</option>
          </Select>
        </div>
        <div className="stock-form-grid">
          <Input
            label="% от прибыли"
            inputMode="decimal"
            value={form.profit}
            onChange={(e) => set({ profit: e.target.value })}
            error={op.fields.profit_bp}
          />
          <Select
            label="От какой прибыли"
            value={form.profit_base}
            onChange={(e) =>
              set({ profit_base: e.target.value as "simple" | "full" })
            }
          >
            <option value="full">Полная (после зарплаты и комиссии)</option>
            <option value="simple">Упрощённая (до зарплаты и комиссии)</option>
          </Select>
        </div>
        <label className="check-label">
          <input
            type="checkbox"
            checked={form.active}
            onChange={(e) => set({ active: e.target.checked })}
          />
          Работает сейчас
        </label>
        {op.error && <Alert>{op.error}</Alert>}
        <Button type="submit" loading={op.busy}>
          Сохранить
        </Button>
      </form>
    </Dialog>
  );
}

function PayDialog({
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
