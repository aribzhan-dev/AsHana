import { PageShell } from "../shared/ui/PageShell";
import { OrderList } from "../features/orders/OrderList";
export function OrdersPage() {
  return (
    <PageShell
      navigation={
        <a href="/" className="header-link desktop-only">
          Меню
        </a>
      }
    >
      <OrderList />
    </PageShell>
  );
}
