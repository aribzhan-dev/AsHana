import { receivingApi, type Directory } from "../../shared/api/receiving";
import { useCallback, useEffect, useRef, useState } from "react";
import { posApi, type PosInput, type Sale } from "../../shared/api/pos";
import { ApiError } from "../../shared/api/http";
import type { PublicEntry } from "../../shared/api/catalog";
import { errorMessage } from "../../shared/lib/forms";
import { stockMoney } from "../../shared/lib/inventory-validation";
import { quantityError } from "../../shared/lib/quantity";
import { posRu as t } from "../../shared/locales/pos";
import { Button } from "../../shared/ui/Button";
import { Input, Select } from "../../shared/ui/Input";
import { QuantityInput } from "../../shared/ui/QuantityInput";
import { Alert, Card, LoadingState, Toast } from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
type Line = { entry: PublicEntry; quantity: string };
type Pending = { key: string; body: PosInput };
function restore(key: string): Pending | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key) || "null");
    if (
      value &&
      typeof value === "object" &&
      "key" in value &&
      typeof value.key === "string" &&
      "body" in value &&
      value.body &&
      typeof value.body === "object" &&
      "lines" in value.body &&
      Array.isArray(value.body.lines) &&
      "outcome" in value.body &&
      ["success", "failed", "timeout"].includes(String(value.body.outcome))
    )
      return value as Pending;
  } catch {
    /* Storage can be unavailable; sending requires a successful write. */
  }
  return null;
}
export function PosBoard({
  userId,
  onExpired,
}: {
  userId: string;
  onExpired: () => void;
}) {
  const [methods, setMethods] = useState<Directory[]>([]);
  const [method, setMethod] = useState("00000000-0000-0000-0000-000000000002");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const storageKey = `ashana.pos.pending.${userId}`;
  const [pending, setPending] = useState<Pending | null>(() =>
    restore(storageKey),
  );
  const [menu, setMenu] = useState<PublicEntry[]>([]);
  const [offset, setOffset] = useState(0);
  const [lines, setLines] = useState<Line[]>([]),
    [confirm, setConfirm] = useState(!!pending);
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState(""),
    [submitError, setSubmitError] = useState("");
  const [result, setResult] = useState<Sale | null>(null);
  const inFlight = useRef(false);
  const refresh = useCallback(async () => {
    async function allMenu() {
      const all: PublicEntry[] = [];
      for (let offset = 0; ; offset += 20) {
        const page = await posApi.menu(offset);
        all.push(...page);
        if (page.length < 20) break;
      }
      return all;
    }
    try {
      const [m, h] = await Promise.all([
        allMenu(),
        receivingApi.paymentMethods(),
      ]);
      setMenu(m);
      setMethods(h);
      setError("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onExpired();
      else setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [onExpired]);
  useEffect(() => {
    void Promise.resolve().then(refresh);
    const timer = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(timer);
  }, [refresh]);
  const total = lines.reduce(
    (n, l) => n + (Number(l.quantity) || 0) * l.entry.price_minor,
    0,
  );
  const valid =
    lines.length > 0 &&
    lines.every((l) => !quantityError(l.quantity, 1, 100)) &&
    lines.reduce((n, l) => n + Number(l.quantity), 0) <= 100;
  function add(entry: PublicEntry) {
    setResult(null);
    setLines((current) => {
      const existing = current.find((l) => l.entry.id === entry.id);
      return existing
        ? current.map((l) =>
            l.entry.id === entry.id
              ? {
                  ...l,
                  quantity: String(
                    Math.min(100, (Number(l.quantity) || 0) + 1),
                  ),
                }
              : l,
          )
        : [...current, { entry, quantity: "1" }];
    });
  }
  async function submit(outcome: PosInput["outcome"]) {
    if (inFlight.current) return;
    const operation = pending || {
      key: crypto.randomUUID(),
      body: {
        outcome,
        payment_method_id: method,
        lines: lines.map((l) => ({
          entry_id: l.entry.id,
          quantity: Number(l.quantity),
          expected_price_minor: l.entry.price_minor,
        })),
      },
    };
    if (!pending && !valid) return;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(operation));
    } catch {
      setSubmitError(t.storage);
      return;
    }
    inFlight.current = true;
    setPending(operation);
    setBusy(true);
    setSubmitError("");
    try {
      const saved = await posApi.sell(operation.body, operation.key);
      sessionStorage.removeItem(storageKey);
      setPending(null);
      setConfirm(false);
      setResult(saved);
      if (saved.outcome === "success") setLines([]);
      void refresh();
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.status >= 400 &&
        e.status < 500 &&
        e.status !== 401 &&
        e.status !== 403
      ) {
        sessionStorage.removeItem(storageKey);
        setPending(null);
        setSubmitError(errorMessage(e));
      } else {
        setSubmitError(
          e instanceof ApiError && (e.status === 401 || e.status === 403)
            ? errorMessage(e)
            : t.uncertain,
        );
        if (e instanceof ApiError && e.status === 401) onExpired();
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="form-stack pos-board">
      {error && <Alert>{error}</Alert>}
      <Button variant="secondary" onClick={() => void refresh()}>
        Обновить кассу
      </Button>
      {loading ? (
        <LoadingState />
      ) : (
        <>
          <div className="pos-layout">
            <section aria-label={t.menu} className="form-stack">
              <div className="pos-toolbar">
                <h2>{t.menu}</h2>
                <Input
                  label="Поиск блюда"
                  placeholder="Название блюда…"
                  leadingIcon="search"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setOffset(0);
                  }}
                />
              </div>
              <div className="category-tabs" aria-label="Категории блюд">
                {[
                  "",
                  ...new Set(menu.map((e) => e.category || "Без категории")),
                ].map((c) => (
                  <Button
                    key={c}
                    variant={category === c ? "primary" : "secondary"}
                    onClick={() => {
                      setCategory(c);
                      setOffset(0);
                    }}
                  >
                    {c || "Все блюда"}
                  </Button>
                ))}
              </div>
              {!menu.length && <p>{t.empty}</p>}
              <div className="catalog-grid">
                {menu
                  .filter(
                    (entry) =>
                      (!category ||
                        (entry.category || "Без категории") === category) &&
                      entry.name
                        .toLocaleLowerCase("ru")
                        .includes(search.toLocaleLowerCase("ru")),
                  )
                  .slice(offset, offset + 20)
                  .map((entry) => (
                    <Card key={entry.id} className="pos-product">
                      <h3>{entry.name}</h3>
                      <p>{entry.portion_label}</p>
                      <p>
                        {stockMoney(entry.price_minor)} · Свободно:{" "}
                        {entry.available}
                      </p>
                      <Button
                        disabled={busy || !!pending || confirm}
                        onClick={() => add(entry)}
                      >
                        Добавить
                      </Button>
                    </Card>
                  ))}
              </div>
              <div className="stock-pagination">
                <Button
                  variant="secondary"
                  disabled={!offset}
                  onClick={() => setOffset(offset - 20)}
                >
                  Назад
                </Button>
                <Button
                  variant="secondary"
                  disabled={
                    offset + 20 >=
                    menu.filter(
                      (e) =>
                        (!category ||
                          (e.category || "Без категории") === category) &&
                        e.name
                          .toLocaleLowerCase("ru")
                          .includes(search.toLocaleLowerCase("ru")),
                    ).length
                  }
                  onClick={() => setOffset(offset + 20)}
                >
                  Далее
                </Button>
              </div>
            </section>
            <Card className="form-stack pos-cart">
              <h2>Текущий чек</h2>
              {!lines.length && <p>{t.noCart}</p>}
              <fieldset
                className="plain-fieldset form-stack"
                disabled={busy || !!pending || confirm}
              >
                {lines.map((line) => (
                  <div key={line.entry.id} className="pos-cart-line">
                    <QuantityInput
                      label={line.entry.name}
                      value={line.quantity}
                      max={100}
                      error={quantityError(line.quantity, 1, 100)}
                      onValueChange={(quantity) =>
                        setLines(
                          lines.map((l) =>
                            l.entry.id === line.entry.id
                              ? { ...l, quantity }
                              : l,
                          ),
                        )
                      }
                    />
                    <p>
                      {stockMoney(line.entry.price_minor)} за{" "}
                      {line.entry.portion_label}
                    </p>
                    <Button
                      variant="ghost"
                      aria-label={`Удалить ${line.entry.name}`}
                      onClick={() =>
                        setLines(
                          lines.filter((l) => l.entry.id !== line.entry.id),
                        )
                      }
                    >
                      Удалить
                    </Button>
                  </div>
                ))}
              </fieldset>
              <p className="pos-total">
                Итого: <strong>{stockMoney(total)}</strong>
              </p>
              <p className="field-hint">
                Не более 100 порций / штук за продажу.
              </p>
              <Button
                disabled={busy || (!pending && !valid)}
                onClick={() => {
                  setSubmitError("");
                  setConfirm(true);
                }}
              >
                {pending ? t.retry : t.checkout}
              </Button>
              {!!lines.length && !pending && (
                <Button
                  variant="secondary"
                  disabled={busy || confirm}
                  onClick={() =>
                    setLines(
                      lines.map((l) => ({
                        ...l,
                        entry: menu.find((e) => e.id === l.entry.id) || l.entry,
                      })),
                    )
                  }
                >
                  Применить цены текущей страницы меню
                </Button>
              )}
            </Card>
          </div>
          {result && (
            <Toast onClose={() => setResult(null)}>
              {t.outcomes[result.outcome]} · {stockMoney(result.total_minor)}
            </Toast>
          )}
        </>
      )}
      {confirm && (
        <Dialog
          open
          title={t.confirm}
          description={t.demo}
          busy={busy || !!pending}
          onClose={() => setConfirm(false)}
        >
          <div className="form-stack">
            {pending ? (
              <p>{t.uncertain}</p>
            ) : (
              <>
                {lines.map((l) => (
                  <p key={l.entry.id}>
                    {l.entry.name} · {l.quantity} ×{" "}
                    {stockMoney(l.entry.price_minor)}
                  </p>
                ))}
                <p className="pos-total">
                  Итого: <strong>{stockMoney(total)}</strong>
                </p>
              </>
            )}
            {!pending && (
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
            )}
            {submitError && <Alert>{submitError}</Alert>}
            {pending ? (
              <Button
                loading={busy}
                onClick={() => void submit(pending.body.outcome)}
              >
                {t.retry}
              </Button>
            ) : (
              <>
                <Button
                  loading={busy}
                  disabled={!methods.some((m) => m.id === method)}
                  onClick={() => void submit("success")}
                >
                  {t.success}
                </Button>
              </>
            )}
          </div>
        </Dialog>
      )}
    </div>
  );
}
