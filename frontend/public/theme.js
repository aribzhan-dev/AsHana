(() => {
  let preference = "system";
  try {
    const saved = localStorage.getItem("ashana-theme");
    if (["light", "dark", "system"].includes(saved)) preference = saved;
  } catch {
    // Storage can be disabled by browser privacy settings.
  }
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme =
    preference === "system" ? (dark ? "dark" : "light") : preference;
})();
