import type { Staff } from "../api/identity";
import { StaffNavigation } from "./StaffNavigation";
import type { ReactNode } from "react";
import { uiRu as t } from "../locales/ui";
import { ru } from "../locales/ru";
import { ThemeSelect } from "./ThemeSelect";
import { Logo } from "./Logo";
import { Icon, type IconName } from "./Icon";

const guestTabs: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Меню", icon: "home" },
  { href: "/orders", label: "Заказы", icon: "receipt" },
  { href: "/orders#qr", label: "QR", icon: "qr" },
];

export function PageShell({
  children,
  navigation,
  staff = false,
  user,
}: {
  children: ReactNode;
  navigation: ReactNode;
  staff?: boolean;
  user?: Staff | null;
}) {
  const path = window.location.pathname;
  return (
    <div
      className={`shell ${staff ? "staff-shell" : "guest-shell"} ${staff && user ? "workspace-shell" : ""}`}
    >
      <a className="skip-link" href="#main">
        {ru.skip}
      </a>
      <header className="header">
        <a href={staff ? "/staff" : "/"} className="brand" aria-label={t.home}>
          <Logo caption={staff ? "Рабочее место" : undefined} />
        </a>
        <nav aria-label={t.navigation}>
          {navigation}
          <ThemeSelect />
        </nav>
      </header>
      {staff && user && <StaffNavigation user={user} />}
      <main id="main" tabIndex={-1} className={staff ? "staff-main" : ""}>
        {children}
      </main>
      {!staff && (
        <nav className="guest-tabbar" aria-label="Разделы для гостя">
          {guestTabs.map((tab) => (
            <a
              key={tab.href}
              href={tab.href}
              aria-current={
                (tab.href === path && window.location.hash !== "#qr") ||
                (tab.href === "/orders#qr" &&
                  path === "/orders" &&
                  window.location.hash === "#qr")
                  ? "page"
                  : undefined
              }
            >
              <Icon name={tab.icon} />
              <span>{tab.label}</span>
            </a>
          ))}
        </nav>
      )}
      {!staff && <footer>{ru.footer}</footer>}
    </div>
  );
}
