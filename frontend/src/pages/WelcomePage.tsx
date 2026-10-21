import { Cart, type CartLine } from "../features/orders/Cart";
import { useEffect, useState } from "react";
import { catalogApi, type PublicMenu } from "../shared/api/catalog";
import { errorMessage } from "../shared/lib/forms";
import { stockDate, stockMoney } from "../shared/lib/inventory-validation";
import { yieldLabel } from "../shared/lib/production-validation";
import { identityRu } from "../shared/locales/identity";
import { catalogRu as t } from "../shared/locales/catalog";
import { inventoryRu as s } from "../shared/locales/inventory";
import { PageShell } from "../shared/ui/PageShell";
import { Button } from "../shared/ui/Button";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
} from "../shared/ui/Feedback";

export function WelcomePage() {
  const [cart, setCart] = useState<CartLine[]>([]),
    [cartError, setCartError] = useState("");
  const [menu, setMenu] = useState<PublicMenu | null>(null),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0),
    [offset, setOffset] = useState(0);
  useEffect(() => {
    let active = true;
    let pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const data = await catalogApi.menu(offset);
        if (active) {
          setMenu(data);
          setError("");
        }
      } catch (cause) {
        if (active) {
          setMenu(null);
          setError(errorMessage(cause));
        }
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 30000);
    const focus = () => void load();
    window.addEventListener("focus", focus);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", focus);
    };
  }, [attempt, offset]);
  function refresh() {
    setMenu(null);
    setError("");
    setAttempt((n) => n + 1);
  }
  return (
    <PageShell
      navigation={
        <>
          <a href="/orders">Мои заказы</a>
          <a href="/staff">{identityRu.staff}</a>
        </>
      }
    >
      <section className="catalog-welcome">
        <p className="eyebrow">{t.publicIntro}</p>
        <h1>{t.publicMenu}</h1>
        <p className="description">{t.publicHint}</p>
        <p className="field-hint">{t.orderNotice}</p>
      </section>
      {cartError && <p role="alert">{cartError}</p>}
      {cart.length > 0 && (
        <Cart key={cart[0]?.entry.period_id} lines={cart} onChange={setCart} />
      )}
      <div className="catalog-toolbar">
        {menu && (
          <p role="status">
            {t.updated}: {stockDate(menu.generated_at)}
          </p>
        )}
        <Button
          variant="secondary"
          disabled={!menu && !error}
          onClick={refresh}
        >
          {t.refresh}
        </Button>
      </div>
      {error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : !menu ? (
        <LoadingState />
      ) : (
        <>
          {!menu.entries.length ? (
            <EmptyState title={t.emptyMenu}>
              <p>{t.emptyHint}</p>
            </EmptyState>
          ) : (
            <div className="catalog-grid">
              {menu.entries.map((entry) => (
                <Card key={entry.id} className="catalog-card">
                  <div>
                    <Badge>{entry.category || entry.period_name}</Badge>
                    <p className="field-hint">
                      {stockDate(entry.starts_at)} — {stockDate(entry.ends_at)}
                    </p>
                  </div>
                  <h2>{entry.name}</h2>
                  {entry.description && <p>{entry.description}</p>}
                  <p className="muted">{entry.portion_label}</p>
                  <div className="catalog-price">
                    <strong>{stockMoney(entry.price_minor)}</strong>
                    <span>
                      {t.availability}:{" "}
                      {yieldLabel(entry.available, entry.unit)}
                    </span>
                  </div>
                  <Button
                    onClick={() => {
                      if (
                        cart.length &&
                        cart[0]?.entry.period_id !== entry.period_id
                      ) {
                        setCartError(
                          "В одном оформлении выбирайте блюда одного периода. Сначала завершите или очистите корзину.",
                        );
                        return;
                      }
                      setCartError("");
                      setCart((current) => {
                        const existing = current.find(
                          (l) => l.entry.id === entry.id,
                        );
                        return existing
                          ? current.map((l) =>
                              l.entry.id === entry.id
                                ? {
                                    ...l,
                                    quantity: Math.min(100, l.quantity + 1),
                                  }
                                : l,
                            )
                          : [...current, { entry, quantity: 1 }];
                      });
                    }}
                  >
                    В корзину
                  </Button>
                </Card>
              ))}
            </div>
          )}
          {(offset > 0 || menu.entries.length === 20) && (
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
                disabled={menu.entries.length < 20}
                onClick={() => {
                  setOffset((n) => n + 20);
                  refresh();
                }}
              >
                {s.next}
              </Button>
            </div>
          )}
          <p className="field-hint">{t.snapshotHint}</p>
        </>
      )}
    </PageShell>
  );
}
