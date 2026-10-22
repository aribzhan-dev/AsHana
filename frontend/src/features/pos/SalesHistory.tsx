import { useEffect, useState } from "react";
import { posApi, type Sale } from "../../shared/api/pos";
import { ordersApi, type Order } from "../../shared/api/orders";
import { stockDate, stockMoney } from "../../shared/lib/inventory-validation";
import { errorMessage } from "../../shared/lib/forms";
import { Button } from "../../shared/ui/Button";
import { Alert, Card, LoadingState } from "../../shared/ui/Feedback";
import { DetailsButton } from "../../shared/ui/DetailsButton";
import { OrderCard } from "../orders/OrderList";
import { ReturnDialog } from "./ReturnDialog";
export function SalesHistory({ permissions }: { permissions: string[] }) {
  const [channel, setChannel] = useState("cashier"),
    [offset, setOffset] = useState(0),
    [sales, setSales] = useState<Sale[]>([]),
    [orders, setOrders] = useState<Order[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [attempt, setAttempt] = useState(0),
    [refund, setRefund] = useState<Sale | null>(null);
  const canRefund = permissions.includes("pos.refund");
  useEffect(() => {
    let active = true;
    void (
      channel === "cashier"
        ? posApi.history(offset).then((v) => {
            if (active) setSales(v);
          })
        : ordersApi.list(true, offset, "closed").then((v) => {
            if (active) setOrders(v);
          })
    )
      .then(() => {
        if (active) setError("");
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
  }, [channel, offset, attempt]);
  return (
    <div className="form-stack">
      <h1>История продаж</h1>
      <div className="button-row">
        <Button
          variant={channel === "cashier" ? "primary" : "secondary"}
          onClick={() => {
            setChannel("cashier");
            setOffset(0);
            setLoading(true);
          }}
        >
          Касса · офлайн
        </Button>
        {permissions.includes("kitchen.read") && (
          <Button
            variant={channel === "online" ? "primary" : "secondary"}
            onClick={() => {
              setChannel("online");
              setOffset(0);
              setLoading(true);
            }}
          >
            Сайт · закрытые заказы
          </Button>
        )}
        <Button variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
          Обновить
        </Button>
      </div>
      {error && <Alert>{error}</Alert>}
      {loading ? (
        <LoadingState />
      ) : (
        <div className="compact-list">
          {channel === "cashier"
            ? sales.map((s) => (
                <Card key={s.id} className="compact-record">
                  <div>
                    <h3>
                      {s.outcome === "success"
                        ? "Выдано"
                        : s.outcome === "failed"
                          ? "Оплата отклонена"
                          : "Оплата не подтверждена"}{" "}
                      · {s.id.slice(0, 8).toUpperCase()}
                    </h3>
                    <p className="muted">
                      {stockDate(s.created_at)} ·{" "}
                      {s.payment_method_name || "Способ не указан"}
                      {s.returned_minor > 0 &&
                        ` · возврат ${stockMoney(s.returned_minor)}`}
                    </p>
                  </div>
                  <strong>{stockMoney(s.total_minor)}</strong>
                  {canRefund &&
                    s.outcome === "success" &&
                    s.returned_minor < s.total_minor && (
                      <Button variant="secondary" onClick={() => setRefund(s)}>
                        Возврат
                      </Button>
                    )}
                  <DetailsButton title={`Чек ${s.id.slice(0, 8)}`}>
                    {s.lines.map((l) => (
                      <p key={l.entry_id}>
                        {l.name} · {l.quantity} × {stockMoney(l.price_minor)}
                      </p>
                    ))}
                    <strong>Итого: {stockMoney(s.total_minor)}</strong>
                  </DetailsButton>
                </Card>
              ))
            : orders.map((o) => (
                <Card key={o.id} className="compact-record">
                  <div>
                    <h3>Заказ {o.id.slice(0, 8)}</h3>
                    <p className="muted">
                      {stockDate(o.slot_starts_at)} ·{" "}
                      {o.status === "completed"
                        ? "Выдан"
                        : o.status === "cancelled"
                          ? "Отменён"
                          : "Не забрали"}
                    </p>
                  </div>
                  <strong>{stockMoney(o.total_minor)}</strong>
                  <DetailsButton title={`Заказ ${o.id.slice(0, 8)}`}>
                    <OrderCard
                      order={o}
                      staff
                      onChanged={() => setAttempt((n) => n + 1)}
                    />
                  </DetailsButton>
                </Card>
              ))}
          {!(channel === "cashier" ? sales : orders).length && (
            <p>Операций пока нет</p>
          )}
        </div>
      )}
      {refund && (
        <ReturnDialog
          sale={refund}
          onClose={() => setRefund(null)}
          onDone={() => {
            setRefund(null);
            setAttempt((n) => n + 1);
          }}
        />
      )}
      <div className="stock-pagination">
        <Button
          variant="secondary"
          disabled={!offset}
          onClick={() => {
            setOffset((n) => n - 20);
            setLoading(true);
          }}
        >
          Назад
        </Button>
        <Button
          variant="secondary"
          disabled={(channel === "cashier" ? sales : orders).length < 20}
          onClick={() => {
            setOffset((n) => n + 20);
            setLoading(true);
          }}
        >
          Далее
        </Button>
      </div>
    </div>
  );
}
