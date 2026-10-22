import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
// Staff enter through /admin; the workspace keeps its /staff/* routes.
if (/^\/admin(\/|$)/.test(window.location.pathname))
  window.history.replaceState(
    null,
    "",
    window.location.pathname.replace(/^\/admin/, "/staff") +
      window.location.search +
      window.location.hash,
  );
const root = document.getElementById("root");
if (!root) throw new Error("Не удалось открыть приложение");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
