import { useEffect, useState } from "react";
import type { PublicEntry } from "../../shared/api/catalog";
import {
  ordersApi,
  type Slot,
  type OrderConfig,
} from "../../shared/api/orders";
import { errorMessage } from "../../shared/lib/forms";
import { stockDate, stockMoney } from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Select, Input } from "../../shared/ui/Input";
import { Alert, Card, LoadingState } from "../../shared/ui/Feedback";
export type CartLine = { entry: PublicEntry; quantity: number };
export function Cart({
  lines,
  onChange,
}: {
  lines: CartLine[];
  onChange: (lines: CartLine[]) => void;
}) {
  const [slots, setSlots] = useState<Slot[]>([]),
    [config, setConfig] = useState<OrderConfig | null>(null),
    [slot, setSlot] = useState(""),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  const op = useOperation(() => {
    window.location.reload();
  });
  const period = lines[0]?.entry.period_id;
  useEffect(() => {
    if (!period) return;
    let active = true;
    void Promise.all([ordersApi.slots(period), ordersApi.config()])
      .then(([slots, config]) => {
        if (active) {
          setSlots(slots);
          setConfig(config);
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
  }, [period, attempt]);
  if (!lines.length) return null;
  async function submit() {
    if (!slot) {
      op.setError("Выберите время получения");
      return;
    }
    const body = {
      slot_id: slot,
      lines: lines.map((l) => ({
        entry_id: l.entry.id,
        quantity: l.quantity,
        expected_price_minor: l.entry.price_minor,
      })),
    };
    if (await op.run(body, (key) => ordersApi.checkout(body, key))) {
      onChange([]);
      window.location.assign("/orders");
    }
  }
  return (
    <Card className="form-stack">
      <h2>Корзина</h2>
      <p>{lines[0]?.entry.period_name}</p>
      <fieldset className="plain-fieldset form-stack" disabled={op.busy}>
        {lines.map((line) => (
          <div className="cart-line" key={line.entry.id}>
            <strong>{line.entry.name}</strong>
            <Input
              label={`Количество: ${line.entry.name}`}
              type="number"
              min={1}
              max={config?.max_portions ?? 100}
              step={1}
              value={line.quantity}
              onChange={(e) => {
                const value = Number(e.target.value);
                if (Number.isSafeInteger(value) && value >= 1 && value <= 100)
                  onChange(
                    lines.map((l) =>
                      l.entry.id === line.entry.id
                        ? { ...l, quantity: value }
                        : l,
                    ),
                  );
              }}
            />
            <Button
              variant="secondary"
              onClick={() =>
                onChange(lines.filter((l) => l.entry.id !== line.entry.id))
              }
            >
              Убрать {line.entry.name}
            </Button>
          </div>
        ))}
        <strong>
          Итого:{" "}
          {stockMoney(
            lines.reduce((sum, l) => sum + l.quantity * l.entry.price_minor, 0),
          )}
        </strong>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <Alert>{error}</Alert>
        ) : (
          <Select
            label="Время получения (Астана)"
            value={slot}
            onChange={(e) => setSlot(e.target.value)}
            required
          >
            <option value="">Выберите время</option>
            {slots.map((s) => (
              <option key={s.id} value={s.id}>
                {stockDate(s.starts_at)} – {stockDate(s.ends_at)} · мест{" "}
                {s.capacity - s.occupied}
              </option>
            ))}
          </Select>
        )}
        {!loading && !error && !slots.length && (
          <p>Нет доступных слотов. Приём заказов закрывается заранее.</p>
        )}
        <Button
          variant="secondary"
          disabled={loading}
          onClick={() => {
            setError("");
            setLoading(true);
            setSlot("");
            setAttempt((n) => n + 1);
          }}
        >
          Обновить время
        </Button>
      </fieldset>
      {config && (
        <p className="field-hint">
          Оплатите минимум за {config.cutoff_minutes} минут до получения.
          Начните оформление ещё на {config.reservation_seconds / 60} минут
          раньше, чтобы получить полное время на оплату. До{" "}
          {config.max_portions} порций в оформлении, до {config.max_active}{" "}
          активных оформлений. Резерв — {config.reservation_seconds / 60} минут.
        </p>
      )}
      <p className="field-hint">
        Сначала резерв и оплата. Заказ появится только после её подтверждения.
        Реальные деньги не списываются.
      </p>
      {op.error && <Alert>{op.error}</Alert>}
      <Button
        loading={op.busy}
        disabled={loading || !slots.length || !!error}
        onClick={() => void submit()}
      >
        Заказать
      </Button>
    </Card>
  );
}
