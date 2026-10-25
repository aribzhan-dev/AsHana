import { useState } from "react";
import {
  basisPoints,
  financeApi,
  percent,
  type FinanceDetails,
  type Pnl,
} from "../../shared/api/finance";
import type { Directory } from "../../shared/api/receiving";
import {
  almatyInstant,
  almatyNow,
  costMinor,
  shortMoney,
} from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Dialog } from "../../shared/ui/Dialog";
import { Alert } from "../../shared/ui/Feedback";
import { Input, Select } from "../../shared/ui/Input";
import { MoneyList } from "./MoneyList";

type Done = () => void;

function MoneyDialog({
  title,
  subjects,
  subjectLabel,
  methods,
  allowNegative = false,
  initial = "",
  submit,
  onClose,
}: {
  title: string;
  subjects: { id: string; name: string }[];
  subjectLabel: string;
  methods: Directory[];
  allowNegative?: boolean;
  initial?: string;
  submit: (
    subject: string,
    amount: number,
    method: string,
    at: string,
    note: string,
    key: string,
  ) => Promise<unknown>;
  onClose: Done;
}) {
  const [subject, setSubject] = useState(subjects[0]?.id ?? ""),
    [sum, setSum] = useState(initial),
    [method, setMethod] = useState(methods[0]?.id ?? ""),
    [at, setAt] = useState(almatyNow()),
    [note, setNote] = useState("");
  const op = useOperation(() => window.location.reload());
  async function save() {
    const negative = allowNegative && sum.trim().startsWith("-");
    const minor = costMinor(sum.replace(/^-/, ""));
    const time = almatyInstant(at);
    if (!minor) {
      op.setFields({ amount_minor: "Введите сумму" });
      return;
    }
    if (!subject || !method || !time) {
      op.setError("Заполните все поля");
      return;
    }
    const value = negative ? -minor : minor;
    if (
      await op.run({ subject, value, method, time, note }, (key) =>
        submit(subject, value, method, time, note, key),
      )
    )
      onClose();
  }
  return (
    <Dialog open title={title} busy={op.busy} onClose={onClose}>
      <form
        className="form-stack"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <Select
          label={subjectLabel}
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
        >
          {subjects.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <Input
          label="Сумма, ₸"
          inputMode="decimal"
          value={sum}
          onChange={(e) => setSum(e.target.value)}
          error={op.fields.amount_minor}
          hint={
            allowNegative ? "Исправление ошибки — со знаком минус." : undefined
          }
        />
        <Select
          label="Способ оплаты"
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
        />
        <Input
          label="Комментарий"
          maxLength={200}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {op.error && <Alert>{op.error}</Alert>}
        <Button type="submit" loading={op.busy}>
          Сохранить
        </Button>
      </form>
    </Dialog>
  );
}

export function ExpensesView({
  details,
  categories,
  methods,
  onChanged,
}: {
  details: FinanceDetails;
  categories: Directory[];
  methods: Directory[];
  onChanged: Done;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="form-stack">
      <div className="button-row">
        <Button icon="plus" onClick={() => setOpen(true)}>
          Добавить расход
        </Button>
      </div>
      <p className="field-hint">
        Аренда, коммунальные услуги, налоги и прочее. Статьи расходов — в
        «Настройки → Статьи расходов».
      </p>
      <MoneyList
        rows={details.expenses.map((e) => ({ ...e, label: e.subject_name }))}
      />
      {open && (
        <MoneyDialog
          title="Расход"
          subjects={categories}
          subjectLabel="Статья расходов"
          methods={methods}
          allowNegative
          submit={(
            category_id,
            amount_minor,
            payment_method_id,
            spent_at,
            note,
            key,
          ) =>
            financeApi.expense(
              { category_id, amount_minor, payment_method_id, spent_at, note },
              key,
            )
          }
          onClose={() => {
            setOpen(false);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

export function OwnersView({
  month,
  pnl,
  details,
  methods,
  onChanged,
}: {
  month: string;
  pnl: Pnl;
  details: FinanceDetails;
  methods: Directory[];
  onChanged: Done;
}) {
  const [base, setBase] = useState<"full" | "simple">("full"),
    [editing, setEditing] = useState<
      FinanceDetails["owners"][number] | "new" | null
    >(null),
    [paying, setPaying] = useState<string | null>(null);
  const profit =
    base === "full" ? pnl.net_profit : pnl.simple_profit - pnl.profit_shares;
  const distributable = Math.max(0, profit);
  return (
    <div className="form-stack">
      <div className="live-row">
        <Select
          label="Прибыль для дивидендов"
          value={base}
          onChange={(e) => setBase(e.target.value as "full" | "simple")}
        >
          <option value="full">Чистая (после зарплаты и комиссии)</option>
          <option value="simple">Упрощённая (до зарплаты и комиссии)</option>
        </Select>
        <div className="kpi">
          <span>К распределению</span>
          <strong>{shortMoney(distributable)}</strong>
        </div>
      </div>
      <div className="button-row">
        <Button icon="plus" onClick={() => setEditing("new")}>
          Добавить учредителя
        </Button>
      </div>
      <div className="table-wrap">
        <table className="report-table">
          <thead>
            <tr>
              <th>Учредитель</th>
              <th className="num">Доля</th>
              <th className="num">Положено</th>
              <th className="num">Выплачено</th>
              <th className="num">Остаток</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {details.owners.map((o) => {
              const due = o.active
                ? Math.round((distributable * o.share_bp) / 10000)
                : 0;
              const paid = details.dividends
                .filter((d) => d.subject_id === o.id)
                .reduce((n, d) => n + d.amount_minor, 0);
              return (
                <tr key={o.id} className={o.active ? "" : "muted"}>
                  <td>{o.name}</td>
                  <td className="num">{percent(o.share_bp)}</td>
                  <td className="num">{shortMoney(due)}</td>
                  <td className="num">{shortMoney(paid)}</td>
                  <td className={`num ${due - paid < 0 ? "debt" : ""}`}>
                    {shortMoney(due - paid)}
                  </td>
                  <td className="row-actions">
                    <Button variant="secondary" onClick={() => setPaying(o.id)}>
                      Выплатить
                    </Button>
                    <Button variant="ghost" onClick={() => setEditing(o)}>
                      Изменить
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <h3>Выплаты дивидендов</h3>
      <MoneyList
        rows={details.dividends.map((d) => ({ ...d, label: d.subject_name }))}
      />
      {editing && (
        <OwnerDialog
          owner={editing === "new" ? null : editing}
          onClose={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
      {paying && (
        <MoneyDialog
          title="Выплата дивидендов"
          subjects={details.owners.filter((o) => o.id === paying)}
          subjectLabel="Учредитель"
          methods={methods}
          submit={(
            owner,
            amount_minor,
            payment_method_id,
            paid_at,
            note,
            key,
          ) =>
            financeApi.dividend(
              owner,
              {
                month: `${month}-01`,
                amount_minor,
                payment_method_id,
                paid_at,
                note,
              },
              key,
            )
          }
          onClose={() => {
            setPaying(null);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function OwnerDialog({
  owner,
  onClose,
}: {
  owner: FinanceDetails["owners"][number] | null;
  onClose: Done;
}) {
  const [name, setName] = useState(owner?.name ?? ""),
    [share, setShare] = useState(owner ? String(owner.share_bp / 100) : ""),
    [active, setActive] = useState(owner?.active ?? true);
  const op = useOperation(() => window.location.reload());
  async function save() {
    const bp = basisPoints(share);
    if (!name.trim() || !bp) {
      op.setFields({ share_bp: "Доля от 0,01 до 100%" });
      return;
    }
    const body = {
      name: name.trim(),
      share_bp: bp,
      active,
      expected_version: owner?.version ?? 0,
    };
    if (
      await op.run({ id: owner?.id, ...body }, (key) =>
        financeApi.owner(owner?.id ?? null, body, key),
      )
    )
      onClose();
  }
  return (
    <Dialog open title="Учредитель" busy={op.busy} onClose={onClose}>
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
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <Input
          label="Доля, %"
          inputMode="decimal"
          value={share}
          onChange={(e) => setShare(e.target.value)}
          error={op.fields.share_bp}
        />
        <label className="check-label">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          Участвует в распределении
        </label>
        {op.error && <Alert>{op.error}</Alert>}
        <Button type="submit" loading={op.busy}>
          Сохранить
        </Button>
      </form>
    </Dialog>
  );
}

export function PlanEditor({
  month,
  details,
  categories,
  onChanged,
}: {
  month: string;
  details: FinanceDetails;
  categories: string[];
  onChanged: Done;
}) {
  const [category, setCategory] = useState(""),
    [target, setTarget] = useState("");
  const op = useOperation(() => window.location.reload());
  async function save() {
    const minor = target.trim() ? costMinor(target) : 0;
    if (minor === undefined) {
      op.setFields({ target_minor: "Введите сумму" });
      return;
    }
    const current = details.plans.find((p) => p.category === category);
    const body = {
      month: `${month}-01`,
      category,
      target_minor: minor,
      expected_version: current?.version ?? 0,
    };
    if (await op.run(body, (key) => financeApi.plan(body, key))) {
      setTarget("");
      onChanged();
    }
  }
  return (
    <form
      className="plan-editor"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <Select
        label="План для"
        value={category}
        onChange={(e) => setCategory(e.target.value)}
      >
        <option value="">Всей столовой</option>
        {categories.map((c) => (
          <option key={c} value={c}>
            Категории «{c}»
          </option>
        ))}
      </Select>
      <Input
        label="Цель на месяц, ₸"
        inputMode="decimal"
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        error={op.fields.target_minor}
      />
      <Button type="submit" loading={op.busy}>
        Сохранить план
      </Button>
      {op.error && <Alert>{op.error}</Alert>}
    </form>
  );
}

export function CommissionEditor({
  methods,
  onChanged,
}: {
  methods: Directory[];
  onChanged: Done;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      methods.map((m) => [m.id, String(m.commission_bp / 100)]),
    ),
  );
  const op = useOperation(() => window.location.reload());
  async function save(id: string) {
    const bp = basisPoints(values[id] ?? "");
    if (bp === undefined) {
      op.setError("Комиссия от 0 до 100%");
      return;
    }
    if (await op.run({ id, bp }, (key) => financeApi.commission(id, bp, key)))
      onChanged();
  }
  return (
    <div className="form-stack">
      {methods.map((m) => (
        <form
          key={m.id}
          className="plan-editor"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void save(m.id);
          }}
        >
          <Input
            label={`${m.name}, комиссия %`}
            inputMode="decimal"
            value={values[m.id] ?? ""}
            onChange={(e) => setValues({ ...values, [m.id]: e.target.value })}
          />
          <Button type="submit" variant="secondary" loading={op.busy}>
            Сохранить
          </Button>
        </form>
      ))}
      {op.error && <Alert>{op.error}</Alert>}
    </div>
  );
}
