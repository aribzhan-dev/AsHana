import { useEffect, useState } from "react";
import { request, ApiError } from "../../shared/api/http";
import { batch, operation, type StockBatch } from "../../shared/api/inventory";
import { stockDate, stockNumber } from "../../shared/lib/inventory-validation";
import { errorMessage } from "../../shared/lib/forms";
import { BatchDialog } from "../inventory/BatchDialog";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { Alert, Card, LoadingState } from "../../shared/ui/Feedback";
export function CashWriteOff({ onExpired }: { onExpired: () => void }) {
  const [rows, setRows] = useState<StockBatch[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [attempt, setAttempt] = useState(0),
    [query, setQuery] = useState(""),
    [selected, setSelected] = useState<StockBatch | null>(null);
  useEffect(() => {
    let active = true;
    async function load() {
      const all: StockBatch[] = [];
      for (let offset = 0; ; offset += 100) {
        const value = await request(`/pos/stock?offset=${offset}&limit=100`);
        if (!Array.isArray(value))
          throw new ApiError(0, "Не удалось загрузить остатки");
        all.push(...value.map(batch));
        if (value.length < 100) break;
      }
      return all;
    }
    void load()
      .then((r) => {
        if (active) {
          setRows(r);
          setError("");
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
  }, [attempt]);
  return (
    <section className="form-stack">
      <h2>Списание готовых товаров</h2>
      <p className="field-hint">
        Укажите количество и причину: срок истёк, порча или не продано. Активные
        резервы списать нельзя.
      </p>
      <Input
        label="Найти товар для списания"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        leadingIcon="search"
      />
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <LoadingState />
      ) : (
        <div className="compact-list">
          {rows
            .filter(
              (b) =>
                Number(b.on_hand) > 0 &&
                b.item_name
                  .toLocaleLowerCase("ru")
                  .includes(query.toLocaleLowerCase("ru")),
            )
            .map((b) => (
              <Card key={b.id} className="compact-record">
                <div>
                  <h3>{b.item_name}</h3>
                  <p className="muted">
                    Годен до: {stockDate(b.expires_at)} ·{" "}
                    {b.status === "expired" ? "Срок истёк" : "Партия"}
                  </p>
                </div>
                <span>
                  Свободно: {stockNumber(b.free)} / В резерве:{" "}
                  {stockNumber(b.reserved)}
                </span>
                <Button
                  variant="danger"
                  disabled={Number(b.free) <= 0}
                  onClick={() => setSelected(b)}
                >
                  Списать
                </Button>
              </Card>
            ))}
        </div>
      )}
      <Button variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
        Обновить остатки
      </Button>
      {selected && (
        <BatchDialog
          batch={selected}
          operation="write_off"
          onExpired={onExpired}
          onClose={() => setSelected(null)}
          onSaved={() => {
            setSelected(null);
            setAttempt((n) => n + 1);
          }}
          change={(id, body, key) =>
            request(`/pos/stock/${id}/write-off`, "POST", body, {
              "Idempotency-Key": key,
            }).then(operation)
          }
        />
      )}
    </section>
  );
}
