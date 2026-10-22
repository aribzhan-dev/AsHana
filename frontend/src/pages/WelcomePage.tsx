import { ProductImage } from "../shared/ui/ProductImage";
import { Cart } from "../features/orders/Cart";
import {
  cartTotal,
  isCutlery,
  type CartLine,
} from "../features/orders/cart-total";
import { ProductSheet } from "../features/catalog/ProductSheet";
import { useEffect, useMemo, useState } from "react";
import {
  catalogApi,
  type PublicEntry,
  type PublicMenu,
} from "../shared/api/catalog";
import { errorMessage } from "../shared/lib/forms";
import { shortMoney } from "../shared/lib/inventory-validation";
import { catalogRu as t } from "../shared/locales/catalog";
import { inventoryRu as s } from "../shared/locales/inventory";
import { PageShell } from "../shared/ui/PageShell";
import { Button, IconButton } from "../shared/ui/Button";
import { Dialog } from "../shared/ui/Dialog";
import { FoodArt } from "../shared/ui/FoodArt";
import { EmptyState, ErrorState, LoadingState } from "../shared/ui/Feedback";
import { Icon } from "../shared/ui/Icon";

const dayFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  timeZone: "Asia/Almaty",
});
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Almaty" });

function periodTitle(entry: PublicEntry): string {
  const start = new Date(entry.starts_at);
  const today = dayKey.format(new Date());
  const tomorrow = dayKey.format(new Date(Date.now() + 86_400_000));
  const key = dayKey.format(start);
  const day =
    key === today
      ? "Сегодня"
      : key === tomorrow
        ? "Завтра"
        : dayFormat.format(start);
  return `${day} · ${entry.period_name}`;
}

export function WelcomePage() {
  const [cart, setCart] = useState<CartLine[]>([]),
    [cartError, setCartError] = useState(""),
    [cartOpen, setCartOpen] = useState(false),
    [selected, setSelected] = useState<PublicEntry | null>(null),
    [category, setCategory] = useState("");
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
  const categories = useMemo(
    () =>
      Array.from(
        new Set(
          menu?.entries
            .filter((e) => !isCutlery(e))
            .map((e) => e.category)
            .filter(Boolean),
        ),
      ).sort((a, b) => a.localeCompare(b, "ru")),
    [menu],
  );
  const visible =
    menu?.entries.filter(
      (e) => !isCutlery(e) && (!category || e.category === category),
    ) ?? [];
  // Today's and tomorrow's periods arrive together; show them as separate days.
  const groups = visible.reduce<
    { id: string; title: string; entries: PublicEntry[] }[]
  >((result, entry) => {
    const group = result.find((g) => g.id === entry.period_id);
    if (group) group.entries.push(entry);
    else
      result.push({
        id: entry.period_id,
        title: periodTitle(entry),
        entries: [entry],
      });
    return result;
  }, []);
  const count = cart
    .filter((l) => !isCutlery(l.entry))
    .reduce((sum, l) => sum + l.quantity, 0);

  function add(entry: PublicEntry, quantity = 1) {
    if (cart.length && cart[0]?.entry.period_id !== entry.period_id) {
      setCartError(
        "В одном заказе выбирайте блюда одного периода. Сначала оформите или очистите корзину.",
      );
      return;
    }
    setCartError("");
    setCart((current) => {
      const existing = current.find((l) => l.entry.id === entry.id);
      const limit = Math.min(10, entry.available);
      return existing
        ? current.map((l) =>
            l.entry.id === entry.id
              ? { ...l, quantity: Math.min(limit, l.quantity + quantity) }
              : l,
          )
        : [...current, { entry, quantity: Math.min(limit, quantity) }];
    });
  }

  return (
    <PageShell
      navigation={
        <a href="/orders" className="header-link desktop-only">
          Мои заказы
        </a>
      }
    >
      <section className="hero">
        <div>
          <h1>Вкусный обед уже ждёт тебя!</h1>
          <p>Закажи заранее и забери без очереди</p>
        </div>
        <FoodArt category="Комплексы" name="" className="hero-art" />
      </section>

      {cartError && (
        <p role="alert" className="inline-alert">
          {cartError}
        </p>
      )}

      {error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : !menu ? (
        <LoadingState />
      ) : !menu.entries.length ? (
        <EmptyState title={t.emptyMenu}>
          <p>{t.emptyHint}</p>
        </EmptyState>
      ) : (
        <>
          {categories.length > 1 && (
            <div className="chips" role="group" aria-label="Категории">
              {["", ...categories].map((c) => (
                <button
                  key={c || "all"}
                  type="button"
                  className="chip"
                  aria-pressed={category === c}
                  onClick={() => setCategory(c)}
                >
                  {c || "Все"}
                </button>
              ))}
            </div>
          )}
          {!groups.length && <EmptyState title="В этой категории пока пусто" />}
          {groups.map((group) => (
            <section key={group.id} aria-label={group.title}>
              <h2 className="section-title">
                {groups.length > 1 || category ? group.title : t.publicMenu}
              </h2>
              <div className="food-grid">
                {group.entries.map((entry) => (
                  <article key={entry.id} className="food-card">
                    <button
                      type="button"
                      className="food-card-open"
                      onClick={() => setSelected(entry)}
                      aria-label={`Подробнее: ${entry.name}`}
                    >
                      <ProductImage
                        src={entry.image_url}
                        category={entry.category}
                        name={entry.name}
                      />
                    </button>
                    <div className="food-card-body">
                      <h3>{entry.name}</h3>
                      <p className="muted">
                        {entry.category || entry.period_name} ·{" "}
                        {entry.portion_label}
                      </p>
                      <div className="food-card-footer">
                        <strong>{shortMoney(entry.price_minor)}</strong>
                        <IconButton
                          icon="plus"
                          className="round-add"
                          label={`Добавить в корзину: ${entry.name}`}
                          onClick={() => add(entry)}
                        />
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
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
        </>
      )}

      {count > 0 && (
        <button
          type="button"
          className="cart-bar"
          onClick={() => setCartOpen(true)}
        >
          <span className="cart-bar-count">
            <Icon name="bag" />
            {count}
          </span>
          <span>Корзина</span>
          <strong>{shortMoney(cartTotal(cart))}</strong>
        </button>
      )}
      {cartOpen && cart.length > 0 && (
        <Dialog
          open
          title="Ваш заказ"
          className="cart-sheet"
          onClose={() => setCartOpen(false)}
        >
          <Cart
            key={cart[0]?.entry.period_id}
            lines={cart}
            cutlery={
              menu?.entries.filter(
                (e) => isCutlery(e) && e.period_id === cart[0]?.entry.period_id,
              ) ?? []
            }
            onChange={(lines) => {
              setCart(lines);
              if (!lines.length) setCartOpen(false);
            }}
          />
        </Dialog>
      )}
      {selected && (
        <ProductSheet
          entry={selected}
          onClose={() => setSelected(null)}
          onAdd={(quantity) => {
            add(selected, quantity);
            setSelected(null);
          }}
        />
      )}
    </PageShell>
  );
}
