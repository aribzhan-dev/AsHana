import type { Staff } from "../api/identity";
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
    label: "Приход",
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
export function StaffNavigation({ user }: { user: Staff }) {
  return (
    <aside className="workspace-sidebar">
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
        <span className="avatar">{user.name.slice(0, 1)}</span>
        <span>
          <strong>{user.name}</strong>
          <small>{user.login}</small>
        </span>
      </a>
    </aside>
  );
}
