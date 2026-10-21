import { useEffect, useState } from "react";
import { applyTheme, readTheme, saveTheme } from "../lib/theme";
import type { Theme } from "../lib/theme";
import { ru } from "../locales/ru";
import { uiRu as t } from "../locales/ui";
import { Button, IconButton } from "./Button";
import { Dialog } from "./Dialog";
import { Icon, type IconName } from "./Icon";

const icons: Record<Theme, IconName> = {
  light: "sun",
  dark: "moon",
  system: "monitor",
};
export function ThemeSelect() {
  const [theme, setTheme] = useState(readTheme);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => applyTheme(theme, media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [theme]);
  useEffect(() => {
    const update = (event: StorageEvent) => {
      if (event.key === "ashana-theme" || event.key === null)
        setTheme(readTheme());
    };
    window.addEventListener("storage", update);
    return () => window.removeEventListener("storage", update);
  }, []);
  return (
    <>
      <IconButton
        variant="secondary"
        className="theme-trigger"
        icon={icons[theme]}
        label={`${ru.theme}: ${ru.themes[theme]}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      />
      <Dialog
        open={open}
        title={t.themeTitle}
        description={t.themeHint}
        onClose={() => setOpen(false)}
      >
        <div className="theme-options">
          {(Object.keys(icons) as Theme[]).map((value) => (
            <Button
              key={value}
              variant="secondary"
              icon={icons[value]}
              aria-pressed={theme === value}
              onClick={() => {
                saveTheme(value);
                setTheme(value);
                setOpen(false);
              }}
            >
              <span>{ru.themes[value]}</span>
              {theme === value && <Icon name="check" />}
            </Button>
          ))}
        </div>
      </Dialog>
    </>
  );
}
