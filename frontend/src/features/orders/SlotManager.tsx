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
} from "../../shared/lib/inventory-validation";
import { errorMessage, focusInvalid } from "../../shared/lib/forms";
import { useOperation } from "../../shared/lib/useOperation";
import { Input, Select } from "../../shared/ui/Input";
import { Button } from "../../shared/ui/Button";
import {
  Alert,
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
const local = (value: string) =>
  new Date(Date.parse(value) + 5 * 3600000).toISOString().slice(0, 16);
const displayDay = (day: string) => day.split("-").reverse().join(".");
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
          label="Начало выдачи (Астана)"
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
      {op.error && <Alert>{op.error}</Alert>}
      <Button type="submit" loading={op.busy}>
        Сохранить слот
      </Button>
    </form>
  );
}
export function SlotManager() {
  const [slotDay, setSlotDay] = useState("");
  const [hour, setHour] = useState("");
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
        label="Дата начала периода (Астана)"
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
              {!slots.length && <EmptyState title="Слотов пока нет" />}
              <div className="slot-toolbar">
                <Select
                  label="День выдачи"
                  value={slotDay}
                  onChange={(e) => {
                    setSlotDay(e.target.value);
                    setHour("");
                  }}
                >
                  <option value="">Все дни</option>
                  {[
                    ...new Set(
                      slots.map((s) => local(s.starts_at).slice(0, 10)),
                    ),
                  ].map((d) => (
                    <option key={d} value={d}>
                      {displayDay(d)}
                    </option>
                  ))}
                </Select>
                <Select
                  label="Час выдачи"
                  value={hour}
                  onChange={(e) => setHour(e.target.value)}
                >
                  <option value="">Все часы</option>
                  {[
                    ...new Set(
                      slots
                        .filter(
                          (s) =>
                            !slotDay || local(s.starts_at).startsWith(slotDay),
                        )
                        .map((s) => local(s.starts_at).slice(11, 13)),
                    ),
                  ].map((h) => (
                    <option key={h} value={h}>
                      {h}:00
                    </option>
                  ))}
                </Select>
                <Button onClick={() => setEditor({})}>Добавить слот</Button>
              </div>
              <div className="slot-grid">
                {slots
                  .filter(
                    (s) =>
                      (!slotDay || local(s.starts_at).startsWith(slotDay)) &&
                      (!hour || local(s.starts_at).slice(11, 13) === hour),
                  )
                  .map((s) => (
                    <button
                      type="button"
                      className="slot-tile"
                      key={s.id}
                      onClick={() => setEditor({ previous: s })}
                      aria-label={`Изменить слот ${local(s.starts_at)}`}
                    >
                      <small>
                        {displayDay(local(s.starts_at).slice(0, 10))}
                      </small>
                      <strong>
                        {local(s.starts_at).slice(11)}–
                        {local(s.ends_at).slice(11)}
                      </strong>
                      <span>
                        {s.enabled
                          ? `${s.occupied} / ${s.capacity} занято`
                          : "Закрыт"}
                      </span>
                      <small>Оплатить до {local(s.cutoff_at).slice(11)}</small>
                    </button>
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
