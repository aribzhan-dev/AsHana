import { useEffect, useState } from "react";
import { ApiError } from "../../shared/api/http";
import {
  catalogApi,
  type Period,
  type MenuEntry,
} from "../../shared/api/catalog";
import { useOperation } from "../../shared/lib/useOperation";
import { errorMessage } from "../../shared/lib/forms";
import {
  almatyNow,
  stockDate,
  stockMoney,
} from "../../shared/lib/inventory-validation";
import { catalogRu as t } from "../../shared/locales/catalog";
import { inventoryRu as s } from "../../shared/locales/inventory";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Toast,
} from "../../shared/ui/Feedback";
import { Dialog } from "../../shared/ui/Dialog";
import { PeriodForm, EntryForm } from "./CatalogForms";

type Editor =
  | { kind: "period"; previous?: Period }
  | { kind: "entry"; previous?: MenuEntry };
export function CatalogBoard({ onExpired }: { onExpired: () => void }) {
  const toggle = useOperation(onExpired);
  const [search, setSearch] = useState("");
  const [day, setDay] = useState(almatyNow().slice(0, 10)),
    [selected, setSelected] = useState<Period | null>(null);
  const [periods, setPeriods] = useState<Period[]>([]),
    [entries, setEntries] = useState<MenuEntry[]>([]),
    [offset, setOffset] = useState(0),
    [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [toast, setToast] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const pending = selected
      ? catalogApi.entries(selected.id, offset).then((data) => {
          if (active) setEntries(data);
        })
      : catalogApi.periods(day, offset).then((data) => {
          if (active) setPeriods(data);
        });
    void pending
      .catch((cause) => {
        if (active) {
          if (cause instanceof ApiError && cause.status === 401) onExpired();
          else setError(errorMessage(cause));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [day, selected, offset, attempt, onExpired]);
  function refresh() {
    setLoading(true);
    setError("");
    setAttempt((n) => n + 1);
  }
  function saved() {
    setEditor(null);
    setBusy(false);
    setToast(t.saved);
    setOffset(0);
    refresh();
  }
  const count = selected ? entries.length : periods.length;
  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">{t.intro}</p>
        <h1>{t.title}</h1>
        <a href="/">{t.menuLink}</a>
      </div>
      {selected ? (
        <>
          <Button
            variant="secondary"
            onClick={() => {
              setSelected(null);
              setOffset(0);
              refresh();
            }}
          >
            {t.back}
          </Button>
          <h2>{selected.name}</h2>
          <p>
            {stockDate(selected.starts_at)} — {stockDate(selected.ends_at)}
          </p>
          <Badge>{selected.published ? t.published : t.draft}</Badge>
        </>
      ) : (
        <Input
          label={t.day}
          type="date"
          value={day}
          onChange={(e) => {
            if (e.target.value) {
              setDay(e.target.value);
              setOffset(0);
              refresh();
            }
          }}
        />
      )}
      <div className="button-row">
        <Button
          icon="plus"
          onClick={() => setEditor({ kind: selected ? "entry" : "period" })}
        >
          {selected ? t.addEntry : t.createPeriod}
        </Button>
        <Button variant="secondary" disabled={loading} onClick={refresh}>
          {t.refresh}
        </Button>
      </div>
      {selected && (
        <Input
          label="Поиск позиции на странице"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Название блюда"
          leadingIcon="search"
        />
      )}
      {toggle.error && <p role="alert">{toggle.error}</p>}
      {toast && <Toast onClose={() => setToast("")}>{toast}</Toast>}
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : (
        <>
          {!count && (
            <EmptyState title={selected ? t.noEntries : t.noPeriods}>
              <p>{selected ? t.publicationHint : t.choosePeriod}</p>
            </EmptyState>
          )}
          <div className="production-grid">
            {selected
              ? entries
                  .filter((entry) =>
                    entry.name
                      .toLocaleLowerCase("ru")
                      .includes(search.toLocaleLowerCase("ru")),
                  )
                  .map((entry) => (
                    <Card key={entry.id} className="production-card">
                      <div className="production-card-heading">
                        <h3>{entry.name}</h3>
                        <Badge>{entry.published ? t.published : t.draft}</Badge>
                      </div>
                      <p>
                        {entry.category || "Без категории"} ·{" "}
                        {entry.description}
                      </p>
                      <div className="production-facts">
                        <div>
                          <span>{t.portion}</span>
                          <strong>{entry.portion_label}</strong>
                        </div>
                        <div>
                          <span>{t.price}</span>
                          <strong>{stockMoney(entry.price_minor)}</strong>
                        </div>
                      </div>
                      <Button
                        variant="secondary"
                        onClick={() =>
                          setEditor({ kind: "entry", previous: entry })
                        }
                      >
                        {t.editEntry}
                      </Button>
                      <Button
                        variant="secondary"
                        loading={toggle.busy}
                        onClick={() => {
                          const body = {
                            item_id: entry.item_id,
                            description: entry.description,
                            category: entry.category,
                            portion_label: entry.portion_label,
                            price_minor: entry.price_minor,
                            expected_version: entry.version,
                            published: !entry.published,
                          };
                          void toggle
                            .run({ id: entry.id, ...body }, (key) =>
                              catalogApi.saveEntry(
                                selected.id,
                                entry.id,
                                body,
                                key,
                              ),
                            )
                            .then((ok) => {
                              if (ok) refresh();
                            });
                        }}
                      >
                        {entry.published
                          ? "Скрыть с сайта"
                          : "Показать на сайте"}
                      </Button>
                    </Card>
                  ))
              : periods.map((period) => (
                  <Card key={period.id} className="production-card">
                    <div className="production-card-heading">
                      <h2>{period.name}</h2>
                      <Badge>{period.published ? t.published : t.draft}</Badge>
                    </div>
                    <p>
                      {stockDate(period.starts_at)} —{" "}
                      {stockDate(period.ends_at)}
                    </p>
                    <div className="button-row">
                      <Button
                        onClick={() => {
                          setSelected(period);
                          setOffset(0);
                          refresh();
                        }}
                      >
                        {t.openPeriod}
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() =>
                          setEditor({ kind: "period", previous: period })
                        }
                      >
                        {t.editPeriod}
                      </Button>
                    </div>
                  </Card>
                ))}
          </div>
          <div className="stock-pagination">
            <Button
              variant="secondary"
              disabled={offset === 0}
              onClick={() => {
                setOffset((n) => Math.max(0, n - 20));
                refresh();
              }}
            >
              {s.previous}
            </Button>
            <span>
              {s.page} {offset / 20 + 1}
            </span>
            <Button
              variant="secondary"
              disabled={count < 20}
              onClick={() => {
                setOffset((n) => n + 20);
                refresh();
              }}
            >
              {s.next}
            </Button>
          </div>
        </>
      )}
      <p className="field-hint">{t.publicationHint}</p>
      {editor && (
        <Dialog
          open
          title={
            editor.kind === "period"
              ? editor.previous
                ? t.editPeriod
                : t.createPeriod
              : editor.previous
                ? t.editEntry
                : t.addEntry
          }
          busy={busy}
          onClose={() => {
            if (!busy) setEditor(null);
          }}
        >
          {editor.kind === "period" ? (
            <PeriodForm
              previous={editor.previous}
              day={day}
              onSaved={saved}
              onExpired={onExpired}
              onBusy={setBusy}
            />
          ) : (
            selected && (
              <EntryForm
                period={selected}
                previous={editor.previous}
                onSaved={saved}
                onExpired={onExpired}
                onBusy={setBusy}
              />
            )
          )}
        </Dialog>
      )}
    </>
  );
}
