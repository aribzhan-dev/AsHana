import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { catalogApi, type Period } from "../../shared/api/catalog";
import {
  ordersApi,
  type Slot,
  type OrderConfig,
} from "../../shared/api/orders";
import {
  almatyInstant,
  almatyNow,
  stockDate,
} from "../../shared/lib/inventory-validation";
import { errorMessage, focusInvalid } from "../../shared/lib/forms";
import { useOperation } from "../../shared/lib/useOperation";
import { Input, Select } from "../../shared/ui/Input";
import { Button } from "../../shared/ui/Button";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
const local = (value: string) =>
  new Date(Date.parse(value) + 5 * 3600000).toISOString().slice(0, 16);
function SlotForm({
  period,
  previous,
  config,
  onSaved,
  onBusy,
}: {
  period: Period;
  previous?: Slot;
  config: OrderConfig;
  onSaved: () => void;
  onBusy: (v: boolean) => void;
}) {
  const op = useOperation(() => window.location.reload());
  useEffect(() => onBusy(op.busy), [op.busy, onBusy]);
  const [starts, setStarts] = useState(
      previous ? local(previous.starts_at) : local(period.starts_at),
    ),
    [minutes, setMinutes] = useState(
      previous
        ? String(
            (Date.parse(previous.ends_at) - Date.parse(previous.starts_at)) /
              60000,
          )
        : String(config.slot_minutes),
    ),
    [capacity, setCapacity] = useState(
      String(previous?.capacity ?? config.slot_capacity),
    ),
    [enabled, setEnabled] = useState(previous?.enabled ?? true);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const start = almatyInstant(starts),
      duration = Number(minutes),
      places = Number(capacity);
    const fields: Record<string, string> = {};
    if (!start) fields.starts_at = "Укажите дату и время";
    if (!/^\d+$/.test(minutes) || duration < 1 || duration > 120)
      fields.ends_at = "От 1 до 120 минут";
    if (!/^\d+$/.test(capacity) || places < 1 || places > 1000)
      fields.capacity = "От 1 до 1000 мест";
    op.setFields(fields);
    if (Object.keys(fields).length || !start) {
      focusInvalid(form);
      return;
    }
    const body = {
      period_id: period.id,
      starts_at: start,
      ends_at: new Date(Date.parse(start) + duration * 60000).toISOString(),
      cutoff_at: new Date(
        Date.parse(start) - config.cutoff_minutes * 60000,
      ).toISOString(),
      capacity: places,
      enabled,
      expected_version: previous?.version ?? 0,
    };
    if (
      await op.run(body, (key) => ordersApi.saveSlot(previous?.id, body, key))
    )
      onSaved();
  }
  return (
    <form className="form-stack" noValidate onSubmit={(e) => void submit(e)}>
      <p>{period.name}</p>
      <fieldset className="plain-fieldset form-stack" disabled={op.busy}>
        <Input
          label="Начало выдачи (Алматы)"
          type="datetime-local"
          value={starts}
          onChange={(e) => setStarts(e.target.value)}
          disabled={!!previous?.occupied}
          error={op.fields.starts_at}
          required
        />
        <Input
          label="Длительность, минут"
          inputMode="numeric"
          value={minutes}
          onChange={(e) => setMinutes(e.target.value)}
          disabled={!!previous?.occupied}
          error={op.fields.ends_at}
          required
        />
        <Input
          label="Максимум заказов в слоте"
          inputMode="numeric"
          value={capacity}
          onChange={(e) => setCapacity(e.target.value)}
          error={op.fields.capacity}
          required
        />
        <label className="production-confirm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          <span>Принимать заказы в этот слот</span>
        </label>
      </fieldset>
      <p className="field-hint">
        Оплата завершается за {config.cutoff_minutes} минут до начала.
        Оформление начинается ещё на {config.reservation_seconds / 60} минут
        раньше. В занятом слоте время менять нельзя.
      </p>
      {op.error && <Alert>{op.error}</Alert>}
      <Button type="submit" loading={op.busy}>
        Сохранить слот
      </Button>
    </form>
  );
}
export function SlotManager() {
  const [day, setDay] = useState(almatyNow().slice(0, 10)),
    [periods, setPeriods] = useState<Period[]>([]),
    [periodId, setPeriodId] = useState(""),
    [slots, setSlots] = useState<Slot[]>([]),
    [config, setConfig] = useState<OrderConfig | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0),
    [editor, setEditor] = useState<{ previous?: Slot } | null>(null),
    [busy, setBusy] = useState(false),
    [periodOffset, setPeriodOffset] = useState(0),
    [more, setMore] = useState(false);
  useEffect(() => {
    let active = true;
    void Promise.all([
      catalogApi.periods(day, periodOffset),
      ordersApi.config(),
      periodId ? ordersApi.slots(periodId, true) : Promise.resolve([]),
    ])
      .then(([p, c, s]) => {
        if (active) {
          setPeriods(p);
          setMore(p.length === 20);
          setConfig(c);
          setSlots(s);
        }
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [day, periodId, attempt, periodOffset]);
  const period = periods.find((p) => p.id === periodId);
  function refresh() {
    setError("");
    setLoading(true);
    setAttempt((n) => n + 1);
  }
  return (
    <div className="form-stack">
      <h2>Время получения</h2>
      <Input
        label="Дата начала периода (Алматы)"
        type="date"
        value={day}
        onChange={(e) => {
          if (e.target.value) {
            setDay(e.target.value);
            setPeriodId("");
            setPeriodOffset(0);
            refresh();
          }
        }}
      />
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : (
        <>
          <Select
            label="Период питания"
            value={periodId}
            onChange={(e) => {
              setPeriodId(e.target.value);
              refresh();
            }}
          >
            <option value="">Выберите период</option>
            {periods.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          {(more || periodOffset > 0) && (
            <div className="button-row">
              <Button
                disabled={!periodOffset}
                onClick={() => {
                  setPeriodOffset((n) => Math.max(0, n - 20));
                  setPeriodId("");
                  refresh();
                }}
              >
                Предыдущие периоды
              </Button>
              <Button
                disabled={!more}
                onClick={() => {
                  setPeriodOffset((n) => n + 20);
                  setPeriodId("");
                  refresh();
                }}
              >
                Ещё периоды
              </Button>
            </div>
          )}
          {period && (
            <>
              <Button onClick={() => setEditor({})}>Добавить слот</Button>
              {!slots.length && <EmptyState title="Слотов пока нет" />}
              <div className="production-grid">
                {slots.map((s) => (
                  <Card key={s.id} className="production-card">
                    <h3>
                      {stockDate(s.starts_at)} — {stockDate(s.ends_at)}
                    </h3>
                    <Badge>{s.enabled ? "Включён" : "Закрыт"}</Badge>
                    <p>Оплатить до {stockDate(s.cutoff_at)}</p>
                    <p>
                      Занято {s.occupied} из {s.capacity}
                    </p>
                    <Button
                      variant="secondary"
                      onClick={() => setEditor({ previous: s })}
                    >
                      Изменить слот
                    </Button>
                  </Card>
                ))}
              </div>
            </>
          )}
        </>
      )}
      {editor && period && config && (
        <Dialog
          open
          title={editor.previous ? "Изменить слот" : "Добавить слот"}
          busy={busy}
          onClose={() => {
            if (!busy) setEditor(null);
          }}
        >
          <SlotForm
            period={period}
            previous={editor.previous}
            config={config}
            onBusy={setBusy}
            onSaved={() => {
              setEditor(null);
              setBusy(false);
              refresh();
            }}
          />
        </Dialog>
      )}
    </div>
  );
}
