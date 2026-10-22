import { useEffect, useState } from "react";
import { Dialog } from "./Dialog";
import { Button } from "./Button";
import { identityApi, type Staff } from "../api/identity";
import { Icon, type IconName } from "./Icon";
const sections: {
  href: string;
  label: string;
  icon: IconName;
  permission?: string;
}[] = [
  { href: "/staff", label: "Обзор", icon: "grid" },
  { href: "/staff/pos", label: "Касса", icon: "bag", permission: "pos.sell" },
  {
    href: "/staff/orders",
    label: "Входящие заказы",
    icon: "clock",
    permission: "kitchen.read",
  },
  {
    href: "/staff/scan",
    label: "Выдача по QR",
    icon: "qr",
    permission: "orders.fulfil",
  },
  {
    href: "/staff/catalog",
    label: "Меню на сайте",
    icon: "eye",
    permission: "catalog.manage",
  },
  {
    href: "/staff/inventory",
    label: "Остатки",
    icon: "box",
    permission: "inventory.manage",
  },
  {
    href: "/staff/production",
    label: "Рецепты и выпуск",
    icon: "utensils",
    permission: "production.manage",
  },
  {
    href: "/staff/reports",
    label: "Отчёты",
    icon: "chart",
    permission: "reporting.read",
  },
  {
    href: "/staff/finance",
    label: "Финансы и зарплата",
    icon: "receipt",
    permission: "finance.manage",
  },
  {
    href: "/staff/team",
    label: "Сотрудники и роли",
    icon: "user",
    permission: "identity.manage",
  },
  {
    href: "/staff/products",
    label: "Товары",
    icon: "box",
    permission: "inventory.manage",
  },
  {
    href: "/staff/receipts",
    label: "Поступления",
    icon: "plus",
    permission: "inventory.manage",
  },
  {
    href: "/staff/sales",
    label: "История продаж",
    icon: "clock",
    permission: "pos.sell",
  },
  {
    href: "/staff/settings",
    label: "Настройки",
    icon: "grid",
    permission: "inventory.manage",
  },
  { href: "/staff/profile", label: "Мой профиль", icon: "user" },
];
function NavigationContent({ user }: { user: Staff }) {
  const [leaving, setLeaving] = useState(false);
  async function logout() {
    setLeaving(true);
    try {
      await identityApi.logout();
    } catch {
      // An expired session is already logged out; the login page handles the rest.
    }
    window.location.assign("/admin");
  }
  return (
    <>
      <p className="sidebar-caption">Рабочее пространство</p>
      <nav aria-label="Разделы управления">
        {sections
          .filter(
            (s) => !s.permission || user.permissions.includes(s.permission),
          )
          .map((s) => (
            <a
              key={s.href}
              href={s.href}
              aria-current={
                window.location.pathname === s.href ? "page" : undefined
              }
            >
              <Icon name={s.icon} />
              <span>{s.label}</span>
            </a>
          ))}
      </nav>
      <a className="sidebar-user" href="/staff/profile">
        <span className="avatar">
          {(user.nickname || user.name).slice(0, 1)}
        </span>
        <span>
          <strong>{user.nickname || user.name}</strong>
          <small>{user.login}</small>
        </span>
      </a>
      <button
        type="button"
        className="sidebar-logout"
        disabled={leaving}
        onClick={() => void logout()}
      >
        <Icon name="logout" />
        <span>Выйти из кабинета</span>
      </button>
    </>
  );
}

export function StaffNavigation({ user }: { user: Staff }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 768px)");
    const close = () => {
      if (media.matches) setOpen(false);
    };
    media.addEventListener("change", close);
    return () => media.removeEventListener("change", close);
  }, []);
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);
  return (
    <>
      <div className="mobile-navigation">
        <Button
          variant="secondary"
          icon="menu"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          Меню
        </Button>
        <span>
          {sections.find((s) => s.href === window.location.pathname)?.label ||
            "AsHana"}
        </span>
      </div>
      <aside className="workspace-sidebar desktop-navigation">
        <NavigationContent user={user} />
      </aside>
      {open && (
        <Dialog
          open
          title="Меню"
          className="navigation-drawer"
          onClose={() => setOpen(false)}
        >
          <aside className="workspace-sidebar">
            <NavigationContent user={user} />
          </aside>
        </Dialog>
      )}
    </>
  );
}
