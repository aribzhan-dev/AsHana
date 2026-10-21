import { useEffect, useState } from "react";
import { ordersApi, type Order } from "../../shared/api/orders";
import { errorMessage } from "../../shared/lib/forms";
import { stockDate, stockMoney } from "../../shared/lib/inventory-validation";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../shared/ui/Feedback";
import { KitchenActions } from "./KitchenActions";
const statuses: Record<Order["status"], string> = {
  pending_payment: "Ожидает тестовой оплаты",
  confirmed: "Принят",
  preparing: "Комплектуется",
  ready: "Готов к выдаче",
  completed: "Выдан",
  cancelled: "Отменён",
  expired: "Резерв истёк",
  no_show: "Не забрали",
};
export function OrderCard({
  order,
  staff,
  checkout = false,
  permissions = [],
  onChanged,
}: {
  order: Order;
  staff: boolean;
  checkout?: boolean;
  permissions?: string[];
  onChanged: () => void;
}) {
  const op = useOperation(() => window.location.reload());
  const [notice, setNotice] = useState("");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (order.status !== "pending_payment") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [order.status]);
  const remaining = Math.max(
    0,
    Math.ceil((Date.parse(order.expires_at) - now) / 1000),
  );
  async function pay(outcome: "success" | "failed" | "timeout") {
    const ok = await op.run({ id: order.id, outcome }, (key) =>
      ordersApi.pay(order.id, outcome, key),
    );
    if (ok) {
      setNotice(
        outcome === "failed"
          ? "Тестовая оплата отклонена. Можно повторить до истечения резерва."
          : outcome === "timeout"
            ? "Тестовый таймаут: успех не подтверждён. Обновите статус перед повтором."
            : "",
      );
      onChanged();
    }
  }
  return (
    <Card className="production-card order-card">
      <div className="production-card-heading">
        <h2>
          {checkout || order.status === "pending_payment"
            ? "Оформление"
            : "Заказ"}{" "}
          {order.id.slice(0, 8)}
        </h2>
        <Badge>{statuses[order.status]}</Badge>
      </div>
      <Badge>ДЕМО · реальные деньги не списываются</Badge>
      {!staff &&
        order.pickup_code &&
        ["confirmed", "preparing", "ready"].includes(order.status) && (
          <p>
            Код получения:{" "}
            <strong data-testid="pickup-code">{order.pickup_code}</strong>.
            Покажите сотруднику при получении.
          </p>
        )}
      {staff && (
        <KitchenActions
          order={order}
          permissions={permissions}
          onChanged={onChanged}
        />
      )}
      {order.stock_issue && (
        <Alert title="Требуется проверка">
          Товар из резерва приостановлен или срок истёк. Обратитесь к
          сотруднику; не выдавайте этот заказ без проверки.
        </Alert>
      )}
      <p>
        Получение: {stockDate(order.slot_starts_at)} —{" "}
        {stockDate(order.slot_ends_at)}
      </p>
      <ul className="production-lines">
        {order.lines.map((l) => (
          <li key={l.entry_id}>
            <span>
              {l.name}
              <small>{l.portion_label}</small>
            </span>
            <strong>
              {l.quantity} × {stockMoney(l.price_minor)}
            </strong>
          </li>
        ))}
      </ul>
      <strong>Итого: {stockMoney(order.total_minor)}</strong>
      {order.status === "pending_payment" && (
        <>
          <p role="timer" aria-label="Осталось времени на оплату">
            На оплату: {Math.floor(remaining / 60)}:
            {String(remaining % 60).padStart(2, "0")}
          </p>
          <p className="field-hint">
            Резерв до {stockDate(order.expires_at)}. Это ещё не заказ; кухня его
            не видит.
          </p>
          {!staff && (
            <div className="button-row">
              <Button disabled={op.busy} onClick={() => void pay("success")}>
                Тестовая оплата: успешно
              </Button>
              <Button
                variant="secondary"
                disabled={op.busy}
                onClick={() => void pay("failed")}
              >
                Тестовая оплата: отказ
              </Button>
              <Button
                variant="secondary"
                disabled={op.busy}
                onClick={() => void pay("timeout")}
              >
                Тестовая оплата: таймаут
              </Button>
            </div>
          )}
        </>
      )}
      {!staff && ["pending_payment", "confirmed"].includes(order.status) && (
        <Button
          variant="secondary"
          loading={op.busy}
          onClick={() =>
            void op
              .run({ cancel: order.id }, () => ordersApi.cancel(order.id))
              .then((ok) => {
                if (ok) onChanged();
              })
          }
        >
          {order.status === "pending_payment"
            ? "Отменить оформление"
            : "Отменить заказ"}
        </Button>
      )}
      {notice && <p role="status">{notice}</p>}
      {op.error && <Alert>{op.error}</Alert>}
    </Card>
  );
}
export function OrderList({
  staff = false,
  permissions = [],
}: {
  staff?: boolean;
  permissions?: string[];
}) {
  const [orders, setOrders] = useState<Order[]>([]),
    [drafts, setDrafts] = useState<Order[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [offset, setOffset] = useState(0),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true,
      pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const [orders, drafts] = await Promise.all([
          ordersApi.list(staff, offset),
          staff ? Promise.resolve([]) : ordersApi.checkouts(offset),
        ]);
        if (active) {
          setOrders(orders);
          setDrafts(drafts);
          setError("");
        }
      } catch (cause) {
        if (active) setError(errorMessage(cause));
      } finally {
        pending = false;
        if (active) setLoading(false);
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [staff, offset, attempt]);
  function refresh() {
    setAttempt((n) => n + 1);
  }
  return (
    <div className="form-stack">
      <div className="button-row">
        <Button variant="secondary" disabled={loading} onClick={refresh}>
          Обновить заказы
        </Button>
      </div>
      <p className="field-hint">
        {staff
          ? "Здесь только заказы после подтверждения тестовой оплаты. Ближайшее время получения — в начале списка, завершённые и отменённые — в конце. Список обновляется каждые 15 секунд. Еда уже приготовлена: здесь порционируют, комплектуют и отмечают тестовую выдачу."
          : "Оформления и заказы доступны в этом браузере. При удалении cookie доступ будет потерян; номер заказа сам по себе не даёт доступа."}
      </p>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : (
        <>
          {!staff && drafts.length > 0 && (
            <>
              <h2>Оформления до оплаты</h2>
              <div className="production-grid">
                {drafts.map((o) => (
                  <OrderCard
                    key={o.id}
                    order={o}
                    staff={false}
                    checkout
                    onChanged={refresh}
                  />
                ))}
              </div>
            </>
          )}
          <h2>Заказы после оплаты</h2>
          {!orders.length && <EmptyState title="Заказов пока нет" />}
          <div className="production-grid">
            {orders.map((o) => (
              <OrderCard
                key={o.id}
                order={o}
                staff={staff}
                permissions={permissions}
                onChanged={refresh}
              />
            ))}
          </div>
          <div className="stock-pagination">
            <Button
              variant="secondary"
              disabled={offset === 0}
              onClick={() => {
                setLoading(true);
                setOffset((n) => Math.max(0, n - 20));
              }}
            >
              Назад
            </Button>
            <span>Страница {offset / 20 + 1}</span>
            <Button
              variant="secondary"
              disabled={orders.length < 20 && drafts.length < 20}
              onClick={() => {
                setLoading(true);
                setOffset((n) => n + 20);
              }}
            >
              Далее
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
