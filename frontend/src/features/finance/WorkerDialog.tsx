import { useState } from "react";
import { basisPoints, financeApi, type Worker } from "../../shared/api/finance";
import { costMinor } from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Dialog } from "../../shared/ui/Dialog";
import { Alert } from "../../shared/ui/Feedback";
import { Input, Select } from "../../shared/ui/Input";

export function WorkerDialog({
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
