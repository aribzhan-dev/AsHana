import { ProductImage } from "../../shared/ui/ProductImage";
import { useEffect, useState } from "react";
import {
  ordersApi,
  type Slot,
  type OrderConfig,
} from "../../shared/api/orders";
import { errorMessage } from "../../shared/lib/forms";
import { shortMoney } from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { Button, IconButton } from "../../shared/ui/Button";
import { Alert, LoadingState } from "../../shared/ui/Feedback";
import { Stepper } from "../catalog/ProductSheet";
import { cartTotal, isCutlery, type CartLine } from "./cart-total";
import type { PublicEntry } from "../../shared/api/catalog";
export type { CartLine };

const time = new Intl.DateTimeFormat("ru-RU", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Almaty",
});
const day = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  weekday: "long",
  timeZone: "Asia/Almaty",
});

export function Cart({
  lines,
  cutlery = [],
  onChange,
}: {
  lines: CartLine[];
  cutlery?: PublicEntry[];
  onChange: (lines: CartLine[]) => void;
}) {
  const [dining, setDining] = useState<"here" | "takeaway">("here");
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
      dining,
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
  const maxPortions = config?.max_portions ?? 10;
  const food = lines.filter((l) => !isCutlery(l.entry));
  function setCutlery(entry: PublicEntry, quantity: number) {
    const rest = lines.filter((l) => l.entry.id !== entry.id);
    onChange(quantity ? [...rest, { entry, quantity }] : rest);
  }
  return (
    <div className="cart">
      <div className="segmented" role="radiogroup" aria-label="Где будете есть">
        {(
          [
            ["here", "В столовой"],
            ["takeaway", "С собой"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={dining === value}
            onClick={() => {
              setDining(value);
              // Eating in needs no cutlery: drop any picked sets.
              if (value === "here") onChange(food);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <fieldset className="plain-fieldset cart-lines" disabled={op.busy}>
        <legend className="visually-hidden">Состав заказа</legend>
        {food.map((line) => (
          <div className="cart-line" key={line.entry.id}>
            <ProductImage
              src={line.entry.image_url}
              category={line.entry.category}
              name={line.entry.name}
              className="cart-art"
            />
            <div className="cart-line-info">
              <strong>{line.entry.name}</strong>
              <span className="muted">
                {shortMoney(line.entry.price_minor)} ·{" "}
                {line.entry.portion_label}
              </span>
            </div>
            <Stepper
              value={line.quantity}
              max={Math.min(maxPortions, line.entry.available)}
              label={`Количество: ${line.entry.name}`}
              onChange={(value) =>
                onChange(
                  lines.map((l) =>
                    l.entry.id === line.entry.id
                      ? { ...l, quantity: value }
                      : l,
                  ),
                )
              }
            />
            <IconButton
              variant="ghost"
              icon="close"
              label={`Убрать ${line.entry.name}`}
              onClick={() =>
                onChange(lines.filter((l) => l.entry.id !== line.entry.id))
              }
            />
          </div>
        ))}
      </fieldset>
      {dining === "takeaway" && (
        <fieldset className="plain-fieldset cutlery" disabled={op.busy}>
          <legend>Приборы и упаковка</legend>
          {!cutlery.length ? (
            <p className="muted">Приборы сейчас не продаются.</p>
          ) : (
            cutlery.map((entry) => {
              const picked =
                lines.find((l) => l.entry.id === entry.id)?.quantity ?? 0;
              return (
                <div className="cutlery-line" key={entry.id}>
                  <span>
                    <strong>{entry.name}</strong>
                    <small className="muted">
                      {shortMoney(entry.price_minor)}
                    </small>
                  </span>
                  <div
                    className="stepper"
                    role="group"
                    aria-label={`Количество: ${entry.name}`}
                  >
                    <IconButton
                      variant="ghost"
                      icon="minus"
                      label={`Меньше: ${entry.name}`}
                      disabled={!picked}
                      onClick={() => setCutlery(entry, picked - 1)}
                    />
                    <output aria-live="polite">{picked}</output>
                    <IconButton
                      variant="ghost"
                      icon="plus"
                      label={`Больше: ${entry.name}`}
                      disabled={picked >= Math.min(10, entry.available)}
                      onClick={() => setCutlery(entry, picked + 1)}
                    />
                  </div>
                </div>
              );
            })
          )}
        </fieldset>
      )}

      <fieldset className="plain-fieldset slot-picker" disabled={op.busy}>
        <legend>Время получения</legend>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <>
            <Alert>{error}</Alert>
            <Button
              variant="secondary"
              onClick={() => {
                setError("");
                setLoading(true);
                setSlot("");
                setAttempt((n) => n + 1);
              }}
            >
              Обновить время
            </Button>
          </>
        ) : !slots.length ? (
          <p className="muted">
            На сегодня свободного времени нет. Попробуйте позже.
          </p>
        ) : (
          <>
            <p className="muted slot-day">
              {day.format(new Date(slots[0]!.starts_at))}
            </p>
            <div className="slot-chips">
              {slots.map((s) => {
                const free = s.capacity - s.occupied;
                return (
                  <label
                    key={s.id}
                    className={`slot-chip ${slot === s.id ? "selected" : ""}`}
                  >
                    <input
                      type="radio"
                      name="pickup-slot"
                      value={s.id}
                      checked={slot === s.id}
                      onChange={() => setSlot(s.id)}
                    />
                    <strong>{time.format(new Date(s.starts_at))}</strong>
                    <small>осталось {free}</small>
                  </label>
                );
              })}
            </div>
          </>
        )}
      </fieldset>

      {config && (
        <p className="field-hint">
          Оплатите заказ в течение {config.reservation_seconds / 60} минут — мы
          придержим блюда для вас.
        </p>
      )}
      {op.error && <Alert>{op.error}</Alert>}
      <div className="cart-footer">
        <span>
          Итого <strong>{shortMoney(cartTotal(lines))}</strong>
        </span>
        <Button
          loading={op.busy}
          disabled={loading || !slots.length || !!error || !food.length}
          onClick={() => void submit()}
        >
          Оформить заказ
        </Button>
      </div>
    </div>
  );
}
