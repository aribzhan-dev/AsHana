import { lazy, Suspense } from "react";
import { WelcomePage } from "../pages/WelcomePage";
const ReportsPage = lazy(() =>
  import("../pages/ReportsPage").then((m) => ({ default: m.ReportsPage })),
);
const PosPage = lazy(() =>
  import("../pages/PosPage").then((m) => ({ default: m.PosPage })),
);
const OrdersPage = lazy(() =>
  import("../pages/OrdersPage").then((m) => ({ default: m.OrdersPage })),
);
const StaffOrdersPage = lazy(() =>
  import("../pages/StaffOrdersPage").then((m) => ({
    default: m.StaffOrdersPage,
  })),
);
const CatalogPage = lazy(() =>
  import("../pages/CatalogPage").then((m) => ({ default: m.CatalogPage })),
);
const ProductionPage = lazy(() =>
  import("../pages/ProductionPage").then((m) => ({
    default: m.ProductionPage,
  })),
);
const InventoryPage = lazy(() =>
  import("../pages/InventoryPage").then((m) => ({ default: m.InventoryPage })),
);
const StaffPage = lazy(() =>
  import("../pages/StaffPage").then((m) => ({ default: m.StaffPage })),
);
import { LoadingState } from "../shared/ui/Feedback";

export function App() {
  return (
    <Suspense fallback={<LoadingState />}>
      {window.location.pathname === "/staff/reports" ? (
        <ReportsPage />
      ) : ["/staff/pos", "/staff/sales"].includes(window.location.pathname) ? (
        <PosPage />
      ) : window.location.pathname === "/orders" ? (
        <OrdersPage />
      ) : window.location.pathname === "/staff/orders" ? (
        <StaffOrdersPage />
      ) : window.location.pathname === "/staff/catalog" ? (
        <CatalogPage />
      ) : window.location.pathname === "/staff/production" ? (
        <ProductionPage />
      ) : [
          "/staff/inventory",
          "/staff/products",
          "/staff/receipts",
          "/staff/settings",
        ].includes(window.location.pathname) ? (
        <InventoryPage />
      ) : ["/staff", "/staff/profile", "/staff/team"].includes(
          window.location.pathname,
        ) ? (
        <StaffPage />
      ) : (
        <WelcomePage />
      )}
    </Suspense>
  );
}
