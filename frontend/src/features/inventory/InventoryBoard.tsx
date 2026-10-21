import { useCallback, useEffect, useState } from "react";
import {
  inventoryApi,
  type StockBatch,
  type StockItem,
  type StockChange,
} from "../../shared/api/inventory";
import { ApiError } from "../../shared/api/http";
import { errorMessage } from "../../shared/lib/forms";
import {
  stockDate,
  stockMoney,
  stockNumber,
} from "../../shared/lib/inventory-validation";
import { inventoryRu as t } from "../../shared/locales/inventory";
import { Button } from "../../shared/ui/Button";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Toast,
} from "../../shared/ui/Feedback";
import { BatchDialog, HistoryDialog } from "./BatchDialog";
import { ItemForm, ReceiptForm } from "./StockForms";

export function InventoryBoard({ onExpired }: { onExpired: () => void }) {
  const [tab, setTab] = useState<"items" | "receipts" | "batches">("batches");
  const [items, setItems] = useState<StockItem[]>([]),
    [batches, setBatches] = useState<StockBatch[]>([]);
  const [page, setPage] = useState(0),
    [attempt, setAttempt] = useState(0),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [more, setMore] = useState(false),
    [itemBusy, setItemBusy] = useState(false),
    [notice, setNotice] = useState(false),
    [updated, setUpdated] = useState("");
  const [dialog, setDialog] = useState<{
      batch: StockBatch;
      operation: StockChange["operation"];
    } | null>(null),
    [history, setHistory] = useState<StockBatch | null>(null);
  const refresh = useCallback(() => {
    setLoading(true);
    setError("");
    setAttempt((value) => value + 1);
  }, []);
  useEffect(() => {
    let active = true;
    void Promise.all([inventoryApi.items(), inventoryApi.batches(page * 20)])
      .then(([nextItems, nextBatches]) => {
        if (active) {
          setItems(nextItems);
          setMore(nextItems.length === 100);
          setBatches(nextBatches);
          setUpdated(new Date().toISOString());
        }
      })
      .catch((cause) => {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 401) onExpired();
        else setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [page, attempt, onExpired]);
  async function loadMoreItems() {
    if (itemBusy) return;
    setItemBusy(true);
    try {
      const next = await inventoryApi.items(items.length);
      setItems((previous) => [...previous, ...next]);
      setMore(next.length === 100);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) onExpired();
      else setError(errorMessage(cause));
    } finally {
      setItemBusy(false);
    }
  }
  function saved() {
    setNotice(true);
    refresh();
  }
  function changePage(next: number) {
    setPage(next);
    setLoading(true);
    setError("");
  }
  return (
    <>
      <div className="page-heading stock-heading">
        <div>
          <p className="eyebrow">AsHana</p>
          <h1>{t.title}</h1>
          <p className="muted">{t.intro}</p>
        </div>
        <Button variant="secondary" loading={loading} onClick={refresh}>
          {t.refresh}
        </Button>
      </div>
      <div className="stock-tabs" role="group" aria-label={t.title}>
        {(["batches", "receipts", "items"] as const).map((code) => (
          <Button
            key={code}
            variant={tab === code ? "primary" : "secondary"}
            aria-pressed={tab === code}
            onClick={() => setTab(code)}
          >
            {t[code]}
          </Button>
        ))}
      </div>
      {notice && <Toast onClose={() => setNotice(false)}>{t.saved}</Toast>}
      {error && <ErrorState message={error} onRetry={refresh} />}
      {loading && <LoadingState />}
      {tab === "items" && (
        <div className="stock-columns">
          <ItemForm onExpired={onExpired} onSaved={refresh} />
          <Card>
            <h2>{t.items}</h2>
            {!items.length && !loading ? (
              <EmptyState title={t.noItems} />
            ) : (
              <ul className="stock-items">
                {items.map((item) => (
                  <li key={item.id}>
                    <strong>{item.name}</strong>
                    <span>
                      {t.kinds[item.kind]} · {t.units[item.unit]}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {more && (
              <Button
                variant="secondary"
                loading={itemBusy}
                onClick={() => void loadMoreItems()}
              >
                {t.moreItems}
              </Button>
            )}
          </Card>
        </div>
      )}
      {tab === "receipts" && (
        <>
          <ReceiptForm items={items} onExpired={onExpired} onSaved={refresh} />
          {more && (
            <Button
              variant="secondary"
              loading={itemBusy}
              onClick={() => void loadMoreItems()}
            >
              {t.moreItems}
            </Button>
          )}
        </>
      )}
      {tab === "batches" && (
        <>
          {updated && (
            <p className="field-hint">
              {t.updated}: {stockDate(updated)}. {t.refreshHint}
            </p>
          )}
          {!batches.length && !loading && !error ? (
            <EmptyState title={t.noBatches}>
              <Button onClick={() => setTab("receipts")}>{t.receive}</Button>
            </EmptyState>
          ) : (
            <div className="stock-batches">
              {batches.map((batch) => (
                <Card key={batch.id} className="stock-batch">
                  <div className="stock-batch-heading">
                    <div>
                      <h2>{batch.item_name}</h2>
                      <p className="muted">{batch.label}</p>
                    </div>
                    <Badge>
                      {t.states[batch.status as keyof typeof t.states]}
                    </Badge>
                  </div>
                  <dl className="stock-balances">
                    {(["on_hand", "reserved", "available"] as const).map(
                      (key, index) => (
                        <div key={key}>
                          <dt>{[t.onHand, t.reserved, t.available][index]}</dt>
                          <dd>
                            {stockNumber(batch[key])}{" "}
                            <small>
                              {t.units[batch.unit as keyof typeof t.units]}
                            </small>
                          </dd>
                        </div>
                      ),
                    )}
                  </dl>
                  <dl className="stock-details">
                    <div>
                      <dt>{t.expires}</dt>
                      <dd>{stockDate(batch.expires_at)}</dd>
                    </div>
                    <div>
                      <dt>{t.source}</dt>
                      <dd>{batch.source}</dd>
                    </div>
                    <div>
                      <dt>{t.cost}</dt>
                      <dd>
                        {batch.item_kind === "prepared"
                          ? t.unknownCost
                          : stockMoney(batch.total_cost_minor)}
                      </dd>
                    </div>
                    <div>
                      <dt>{t.received}</dt>
                      <dd>{stockDate(batch.received_at)}</dd>
                    </div>
                  </dl>
                  <div className="stock-actions">
                    <Button
                      variant="secondary"
                      onClick={() => setHistory(batch)}
                    >
                      {t.history}
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={loading || batch.status === "written_off"}
                      onClick={() => setDialog({ batch, operation: "count" })}
                    >
                      {t.count}
                    </Button>
                    <Button
                      variant="danger"
                      disabled={
                        loading ||
                        Number(batch.on_hand) === 0 ||
                        batch.status === "written_off"
                      }
                      onClick={() =>
                        setDialog({ batch, operation: "write_off" })
                      }
                    >
                      {t.writeOff}
                    </Button>
                    {["active", "exhausted", "suspended"].includes(
                      batch.status,
                    ) && (
                      <Button
                        variant="secondary"
                        disabled={loading}
                        onClick={() =>
                          setDialog({
                            batch,
                            operation:
                              batch.status === "suspended"
                                ? "resume"
                                : "suspend",
                          })
                        }
                      >
                        {batch.status === "suspended" ? t.resume : t.suspend}
                      </Button>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
          <div className="stock-pagination">
            <Button
              variant="secondary"
              disabled={loading || page === 0}
              onClick={() => changePage(page - 1)}
            >
              {t.previous}
            </Button>
            <span>
              {t.page} {page + 1}
            </span>
            <Button
              variant="secondary"
              disabled={loading || batches.length < 20}
              onClick={() => changePage(page + 1)}
            >
              {t.next}
            </Button>
          </div>
        </>
      )}
      {dialog && (
        <BatchDialog
          batch={dialog.batch}
          operation={dialog.operation}
          onClose={() => setDialog(null)}
          onSaved={saved}
          onExpired={onExpired}
        />
      )}
      {history && (
        <HistoryDialog
          batch={history}
          onClose={() => setHistory(null)}
          onExpired={onExpired}
        />
      )}
    </>
  );
}
