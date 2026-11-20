(() => {
  const storageKey = "shulvrongtong.sidebar.collapsed";
  const body = document.body;
  const button = document.querySelector("[data-sidebar-toggle]");
  const sidebar = document.getElementById("sidebar");

  if (!button || !sidebar) return;

  const saved = window.localStorage.getItem(storageKey);
  const initiallyCollapsed = saved === "true" || (saved === null && window.innerWidth < 1120);

  const applyState = (collapsed, persist = true) => {
    body.classList.toggle("nav-collapsed", collapsed);
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute("aria-label", collapsed ? "展开目录" : "收起目录");
    sidebar.setAttribute("aria-hidden", String(collapsed));
    if (persist) window.localStorage.setItem(storageKey, String(collapsed));
  };

  applyState(initiallyCollapsed, false);
  button.addEventListener("click", () => applyState(!body.classList.contains("nav-collapsed")));

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !body.classList.contains("nav-collapsed")) applyState(true);
  });

  sidebar.addEventListener("click", (event) => {
    if (window.innerWidth < 860 && event.target.closest("a")) applyState(true);
  });
})();
