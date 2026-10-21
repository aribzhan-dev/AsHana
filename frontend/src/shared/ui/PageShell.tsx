import type { ReactNode } from "react";
import { uiRu as t } from "../locales/ui";
import { ru } from "../locales/ru";
import { ThemeSelect } from "./ThemeSelect";

export function PageShell({
  children,
  navigation,
  staff = false,
}: {
  children: ReactNode;
  navigation: ReactNode;
  staff?: boolean;
}) {
  return (
    <div className={`shell ${staff ? "staff-shell" : ""}`}>
      <a className="skip-link" href="#main">
        {ru.skip}
      </a>
      <header className="header">
        <a href="/" className="brand" aria-label={t.home}>
          <span className="brand-mark" aria-hidden="true">
            а
          </span>
          <span>
            <span className="brand-name">{ru.brand}</span>
            <span className="brand-caption">{ru.subtitle}</span>
          </span>
        </a>
        <nav aria-label={t.navigation}>
          {navigation}
          <ThemeSelect />
        </nav>
      </header>
      <main id="main" tabIndex={-1} className={staff ? "staff-main" : ""}>
        {children}
      </main>
      <footer>{ru.footer}</footer>
    </div>
  );
}
