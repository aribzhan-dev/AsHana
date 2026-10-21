import { PageShell } from "../shared/ui/PageShell";
import { OrderList } from "../features/orders/OrderList";
export function OrdersPage() {
  return (
    <PageShell navigation={<a href="/">Меню</a>}>
      <div className="page-heading">
        <p className="eyebrow">Ваше питание</p>
        <h1>Мои заказы</h1>
      </div>
      <OrderList />
    </PageShell>
  );
}
