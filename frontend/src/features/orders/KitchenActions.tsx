import { useState } from "react";
import {
  ordersApi,
  type Order,
  type KitchenTransition,
} from "../../shared/api/orders";
import { useOperation } from "../../shared/lib/useOperation";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { Dialog } from "../../shared/ui/Dialog";
import { Alert } from "../../shared/ui/Feedback";

export function KitchenActions({
  order,
  permissions,
  onChanged,
}: {
  order: Order;
  permissions: string[];
  onChanged: () => void;
}) {
  const op = useOperation(() => window.location.reload());
  const [confirm, setConfirm] = useState(false),
    [code, setCode] = useState("");
  const target =
    order.status === "confirmed"
      ? "preparing"
      : order.status === "preparing"
        ? "ready"
        : order.status === "ready"
          ? "completed"
          : null;
  const allowed =
    target &&
    permissions.includes(
      target === "completed" ? "orders.fulfil" : "kitchen.manage",
    );
  async function advance() {
    if (!target) return;
    if (target === "completed" && !/^[0-9A-F]{8}$/.test(code.trim())) {
      op.setFields({
        pickup_code: "Введите 8 символов кода с экрана посетителя",
      });
      return;
    }
    const body: KitchenTransition = {
      target,
      expected_version: order.version,
      pickup_code: target === "completed" ? code.trim() : "",
    };
    if (
      await op.run({ id: order.id, ...body }, (key) =>
        ordersApi.transition(order.id, body, key),
      )
    ) {
      setConfirm(false);
      setCode("");
      onChanged();
    }
  }
  return (
    <>
      {allowed && (
        <Button
          loading={op.busy}
          disabled={order.stock_issue}
          onClick={() =>
            target === "completed" ? setConfirm(true) : void advance()
          }
        >
          {target === "preparing"
            ? "Начать комплектацию"
            : target === "ready"
              ? "Готов к выдаче"
              : "Выдать заказ"}
        </Button>
      )}
      {op.error && !confirm && <Alert>{op.error}</Alert>}
      {confirm && (
        <Dialog
          open={confirm}
          title="Подтвердить выдачу"
          busy={op.busy}
          onClose={() => setConfirm(false)}
        >
          <form
            className="form-stack"
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              void advance();
            }}
          >
            <p>
              Сверьте состав заказа {order.id.slice(0, 8)} и код на экране
              посетителя. После подтверждения готовые порции будут списаны один
              раз.
            </p>
            <Input
              label="Код получения"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              autoComplete="off"
              maxLength={8}
              required
              error={op.fields.pickup_code}
              disabled={op.busy}
              placeholder="Например, A12B34CD"
            />
            {op.error && <Alert>{op.error}</Alert>}
            <Button type="submit" loading={op.busy}>
              Подтвердить выдачу
            </Button>
          </form>
        </Dialog>
      )}
    </>
  );
}
