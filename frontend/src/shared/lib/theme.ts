export type Theme = "light" | "dark" | "system";

export function isTheme(value: string | null): value is Theme {
  return value === "light" || value === "dark" || value === "system";
}

export function readTheme(): Theme {
  try {
    const saved = localStorage.getItem("ashana-theme");
    return isTheme(saved) ? saved : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(theme: Theme, systemDark: boolean): void {
  document.documentElement.dataset.theme =
    theme === "system" ? (systemDark ? "dark" : "light") : theme;
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem("ashana-theme", theme);
  } catch {
    // The selected theme remains usable when persistence is unavailable.
  }
}
