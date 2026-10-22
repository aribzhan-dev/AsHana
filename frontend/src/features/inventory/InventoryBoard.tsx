import { Dialog } from "../../shared/ui/Dialog";
import { receivingApi, type Directory } from "../../shared/api/receiving";
import { DetailsButton } from "../../shared/ui/DetailsButton";
import { displayText } from "../../shared/lib/display-text";
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
import { Input, Select } from "../../shared/ui/Input";
import { Button, IconButton } from "../../shared/ui/Button";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Toast,
} from "../../shared/ui/Feedback";
import { BatchDialog, HistoryDialog } from "./BatchDialog";
import { ItemForm } from "./StockForms";

export function InventoryBoard({ onExpired }: { onExpired: () => void }) {
  const [itemEditor, setItemEditor] = useState<{ previous?: StockItem } | null>(
    null,
  );
  const [editorBusy, setEditorBusy] = useState(false);
  const [warehouses, setWarehouses] = useState<Directory[]>([]);
  const [warehouse, setWarehouse] = useState("");
  const [batchQuery, setBatchQuery] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [tab, setTab] = useState<"items" | "batches">(
    window.location.pathname.endsWith("/products") ? "items" : "batches",
  );
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
    void Promise.all([
      inventoryApi.items(),
      inventoryApi.batches(page * 20, warehouse, batchQuery),
      receivingApi.directories("warehouse"),
    ])
      .then(([nextItems, nextBatches, ws]) => {
        if (active) {
          setItems(nextItems);
          setWarehouses(ws);
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
  }, [page, attempt, onExpired, warehouse, batchQuery]);
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
          <h1>{tab === "items" ? "Товары" : t.title}</h1>
          <p className="muted">{t.intro}</p>
        </div>
        <Button variant="secondary" loading={loading} onClick={refresh}>
          {t.refresh}
        </Button>
      </div>
      <div className="stock-tabs" role="group" aria-label={t.title}>
        {(["batches", "items"] as const).map((code) => (
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
        <div className="form-stack">
          <div className="button-row">
            <Button icon="plus" onClick={() => setItemEditor({})}>
              Создать товар
            </Button>
            <a className="button button-secondary" href="/staff/receipts">
              Поступления
            </a>
          </div>
          <Card>
            <h2>{t.items}</h2>
            <div className="form-stack">
              <Input
                label="Найти товар"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                leadingIcon="search"
                placeholder="Название товара"
              />
              <Select
                label="Тип товара"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
              >
                <option value="">Все типы</option>
                {Object.entries(t.kinds).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>
            {!items.length && !loading ? (
              <EmptyState title={t.noItems} />
            ) : (
              <ul className="stock-items">
                {items
                  .filter(
                    (item) =>
                      (!kind || item.kind === kind) &&
                      item.name
                        .toLocaleLowerCase("ru")
                        .includes(query.toLocaleLowerCase("ru")),
                  )
                  .map((item) => (
                    <li key={item.id} className="product-list-row">
                      <div className="product-list-info">
                        <strong>{item.name}</strong>
                        <span>
                          {t.kinds[item.kind]} · {t.units[item.unit]}
                          {item.barcode ? ` · ${item.barcode}` : ""}
                        </span>
                      </div>
                      <div className="product-list-actions">
                        <DetailsButton title={item.name}>
                          <dl className="stock-meta">
                            <div>
                              <dt>Категория</dt>
                              <dd>{item.category || "Без категории"}</dd>
                            </div>
                            <div>
                              <dt>Тип / единица</dt>
                              <dd>
                                {t.kinds[item.kind]} · {t.units[item.unit]}
                              </dd>
                            </div>
                            <div>
                              <dt>Закупочная цена</dt>
                              <dd>
                                {stockMoney(item.purchase_price_minor || 0)}
                              </dd>
                            </div>
                            <div>
                              <dt>Цена продажи</dt>
                              <dd>{stockMoney(item.sale_price_minor || 0)}</dd>
                            </div>
                            <div>
                              <dt>Штрихкод</dt>
                              <dd>{item.barcode || "Не указан"}</dd>
                            </div>
                          </dl>
                        </DetailsButton>
                        <IconButton
                          variant="secondary"
                          icon="edit"
                          label={`Редактировать: ${item.name}`}
                          onClick={() => setItemEditor({ previous: item })}
                        />
                      </div>
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
      {tab === "batches" && (
        <>
          <div className="report-filters">
            <Input
              label="Поиск по остаткам"
              leadingIcon="search"
              value={batchQuery}
              onChange={(e) => {
                setBatchQuery(e.target.value);
                setPage(0);
              }}
            />
            <Select
              label="Склад"
              value={warehouse}
              onChange={(e) => {
                setWarehouse(e.target.value);
                setPage(0);
              }}
            >
              <option value="">Все склады</option>
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </div>
          {updated && (
            <p className="field-hint">
              {t.updated}: {stockDate(updated)}
            </p>
          )}
          {!batches.length && !loading && !error ? (
            <EmptyState title={t.noBatches}>
              <a href="/staff/receipts">Открыть приход</a>
            </EmptyState>
          ) : (
            <div className="stock-batches">
              {batches.map((batch) => (
                <Card key={batch.id} className="stock-batch compact-batch">
                  <div className="stock-batch-heading">
                    <div>
                      <h2>{batch.item_name}</h2>
                      <p className="muted">
                        {displayText(batch.label)} ·{" "}
                        {warehouses.find((w) => w.id === batch.warehouse_id)
                          ?.name || "Основной склад"}
                      </p>
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
                  <DetailsButton title={batch.item_name}>
                    <dl className="stock-details">
                      <div>
                        <dt>{t.expires}</dt>
                        <dd>{stockDate(batch.expires_at)}</dd>
                      </div>
                      <div>
                        <dt>{t.source}</dt>
                        <dd>{displayText(batch.source)}</dd>
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
                  </DetailsButton>
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
      {itemEditor && (
        <Dialog
          open
          title={itemEditor.previous ? "Редактировать товар" : "Создать товар"}
          busy={editorBusy}
          onClose={() => {
            if (!editorBusy) setItemEditor(null);
          }}
        >
          <ItemForm
            previous={itemEditor.previous}
            onBusy={setEditorBusy}
            onExpired={onExpired}
            onSaved={() => {
              setItemEditor(null);
              saved();
            }}
          />
        </Dialog>
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
