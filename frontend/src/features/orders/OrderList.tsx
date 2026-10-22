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
import { CardPayment } from "./CardPayment";
import { KitchenLive } from "./KitchenLive";
import { GuestLive } from "./GuestLive";
import { orderNumber, pickupPayload } from "../../shared/lib/pickup-qr";
import { QrCode } from "../../shared/ui/QrCode";
import { Icon } from "../../shared/ui/Icon";
const steps = ["confirmed", "preparing", "ready", "completed"] as const;
const stepLabels = ["Принят", "Собираем", "Готов", "Выдан"];
const pickupTime = new Intl.DateTimeFormat("ru-RU", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Almaty",
});
const pickupDay = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  timeZone: "Asia/Almaty",
});
const statuses: Record<Order["status"], string> = {
  pending_payment: "Ожидает оплаты",
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
  const [notice, setNotice] = useState(""),
    [paying, setPaying] = useState(false);
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
    let paymentStatus = order.status;
    const ok = await op.run({ id: order.id, outcome }, async (key) => {
      const result = await ordersApi.pay(order.id, outcome, key);
      paymentStatus = result.status;
      return result;
    });
    if (ok) {
      setPaying(false);
      setNotice(
        paymentStatus === "pending_payment"
          ? "Оплата не подтверждена. Можно повторить до истечения резерва."
          : "",
      );
      onChanged();
    }
  }
  const active =
    !staff &&
    order.pickup_code &&
    ["confirmed", "preparing", "ready"].includes(order.status);
  const step = steps.indexOf(order.status as (typeof steps)[number]);
  return (
    <Card
      className={`production-card order-card ${active ? "order-ticket" : ""}`}
    >
      {active && (
        <div className="ticket-head">
          <span className="success-badge" aria-hidden="true">
            <Icon name="check" />
          </span>
          <h2>Заказ оформлен!</h2>
          <p className="muted">Ваш заказ №{orderNumber(order.id)}</p>
          <div className="badges centered">
            <Badge>{statuses[order.status]}</Badge>
            <Badge>
              {order.dining === "takeaway" ? "С собой" : "В столовой"}
            </Badge>
          </div>
        </div>
      )}
      {!active && (
        <div className="production-card-heading">
          <h2>
            {checkout || order.status === "pending_payment"
              ? "Оформление"
              : "Заказ"}{" "}
            №{orderNumber(order.id)}
          </h2>
          <div className="badges">
            <Badge>{statuses[order.status]}</Badge>
            {order.dining === "takeaway" && <Badge>С собой</Badge>}
          </div>
        </div>
      )}
      {active && step >= 0 && (
        <ol className="order-steps" aria-label="Статус заказа">
          {stepLabels.map((label, index) => (
            <li
              key={label}
              className={index <= step ? "done" : ""}
              aria-current={index === step ? "step" : undefined}
            >
              {label}
            </li>
          ))}
        </ol>
      )}
      {active && (
        <div className="pickup-box">
          <Icon name="clock" />
          <div>
            <small>Время получения</small>
            <strong>
              {pickupTime.format(new Date(order.slot_starts_at))} –{" "}
              {pickupTime.format(new Date(order.slot_ends_at))}
            </strong>
            <small>{pickupDay.format(new Date(order.slot_starts_at))}</small>
          </div>
        </div>
      )}
      {active && order.pickup_code && (
        <div className="qr-box" id={`qr-${order.id}`}>
          <QrCode
            value={pickupPayload(order.id, order.pickup_code)}
            label={`QR-код заказа №${orderNumber(order.id)}`}
            size={196}
          />
          <p>
            {order.status === "ready"
              ? "Заказ готов! Поднесите QR-код к сканеру на стойке выдачи"
              : "Покажите QR-код на стойке выдачи"}
          </p>
          <p className="pickup-code">
            Код: <strong data-testid="pickup-code">{order.pickup_code}</strong>
          </p>
        </div>
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
      {!active && (
        <p className="muted">
          Получение: {stockDate(order.slot_starts_at)} —{" "}
          {stockDate(order.slot_ends_at)}
        </p>
      )}
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
          {!staff && (
            <div className="button-row">
              <Button disabled={op.busy} onClick={() => setPaying(true)}>
                Оплатить заказ
              </Button>
            </div>
          )}
          {paying && (
            <CardPayment
              total={order.total_minor}
              busy={op.busy}
              error={op.error}
              onPay={(outcome) => void pay(outcome)}
              onClose={() => setPaying(false)}
            />
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
          ordersApi.list(staff, offset, staff ? "active" : "all"),
          staff ? Promise.resolve([]) : ordersApi.checkouts(offset),
        ]);
        if (active) {
          setOrders(orders);
          setDrafts(drafts);
          setError("");
          if (!staff && window.location.hash === "#qr")
            window.requestAnimationFrame(() =>
              document
                .querySelector(".qr-box")
                ?.scrollIntoView({ block: "center" }),
            );
        }
      } catch (cause) {
        if (active) setError(errorMessage(cause));
      } finally {
        pending = false;
        if (active) setLoading(false);
      }
    }
    void load();
    // Reloads come from live signals (KitchenLive / GuestLive) with polling as fallback.
    return () => {
      active = false;
    };
  }, [staff, offset, attempt]);
  function refresh() {
    setAttempt((n) => n + 1);
  }
  return (
    <div className={`form-stack ${staff ? "" : "guest-orders"}`}>
      {staff ? (
        <KitchenLive onReload={refresh} />
      ) : (
        <GuestLive onReload={refresh} />
      )}
      <div className="button-row">
        <Button variant="secondary" disabled={loading} onClick={refresh}>
          Обновить заказы
        </Button>
      </div>
      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : (
        <>
          {!staff && drafts.length > 0 && (
            <>
              <h2>Ожидают оплаты</h2>
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
          {staff && (
            <div className="kds-counters" aria-label="Сводка заказов">
              {(
                [
                  ["confirmed", "Новые", "bell"],
                  ["preparing", "Собираются", "utensils"],
                  ["ready", "Готовы", "check"],
                ] as const
              ).map(([status, label, icon]) => (
                <div key={status} className={`kds-counter kds-${status}`}>
                  <Icon name={icon} />
                  <span>{label}</span>
                  <strong>
                    {orders.filter((o) => o.status === status).length}
                  </strong>
                </div>
              ))}
            </div>
          )}
          <h2>{staff ? "Заказы" : "Мои заказы"}</h2>
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
