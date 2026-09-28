// ==========================================================================
// main.js — shared across every page: computes a runtime site root (so
// other scripts can build working links regardless of how deep the page
// lives or where the site is hosted), handles dark mode, highlights the
// active nav link, and wires up the font-size control.
//
// The navbar/footer are now inlined directly into each HTML page (not
// fetched at runtime), so the site works whether it's opened directly as
// a file, served from a local dev server, or deployed under a sub-path —
// no CORS/fetch restrictions to worry about.
// ==========================================================================

const FH_STORAGE = {
  theme: "fh_theme",
  fontSize: "fh_font_size",
};

// Resolve the project root as an absolute URL by looking at the <script>
// tag that loaded this very file. Works for file://, a local dev server,
// or a production domain, and regardless of page nesting depth.
function computeSiteRoot() {
  const scripts = document.getElementsByTagName("script");
  for (const s of scripts) {
    const idx = s.src.indexOf("/js/main.js");
    if (idx !== -1) return s.src.slice(0, idx + 1); // includes trailing slash
  }
  return "./";
}
window.FH_ROOT = computeSiteRoot();

const ICON_MOON =
  '<svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5 9 9 0 1 0 20.5 14.5Z"/></svg>';
const ICON_SUN =
  '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.5" fill="currentColor" stroke="none"/><path d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6"/></svg>';

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(FH_STORAGE.theme, theme);
  const toggleBtn = document.getElementById("dark-mode-toggle");
  if (toggleBtn) toggleBtn.innerHTML = theme === "dark" ? ICON_MOON : ICON_SUN;
}

function initTheme() {
  const saved = localStorage.getItem(FH_STORAGE.theme) || "dark";
  applyTheme(saved);
}

function wireThemeToggle() {
  const toggleBtn = document.getElementById("dark-mode-toggle");
  if (!toggleBtn) return;
  toggleBtn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    applyTheme(current === "dark" ? "light" : "dark");
  });
}

function applyFontSize(size) {
  document.documentElement.style.fontSize = size + "px";
  localStorage.setItem(FH_STORAGE.fontSize, size);
}

function initFontSize() {
  const saved = localStorage.getItem(FH_STORAGE.fontSize) || 16;
  applyFontSize(saved);
}

// Which bottom-nav tab should light up for the current page. Checked in
// order, first match wins.
const TAB_ROUTES = [
  { tab: "home", files: ["index.html"] },
  { tab: "create", files: ["fan-submissions.html"] },
  { tab: "bookmarks", files: ["bookmarks.html"] },
  {
    tab: "profile",
    files: [
      "profile.html", "dashboard.html", "login.html", "register.html",
      "forgot-password.html", "feedback.html", "sitemap.html",
      "admin-dashboard.html", "usage-stats.html", "moderate-submissions.html",
      "manage-users.html", "manage-content.html",
    ],
  },
  {
    tab: "explore",
    files: [
      "category.html", "content-detail.html", "articles.html",
      "character-profiles.html", "multimedia-center.html", "merchandise.html",
      "upcoming-releases.html", "events-calendar.html",
    ],
  },
];

function highlightActiveTab() {
  const path = window.location.pathname;
  const file = path.split("/").pop() || "index.html";
  const match = TAB_ROUTES.find((r) => r.files.includes(file));
  if (!match) return;
  document.querySelectorAll(".fh-tab").forEach((a) => {
    a.classList.toggle("active", a.dataset.tab === match.tab);
  });
}

// ---- Auth-aware navigation ------------------------------------------------
const PROTECTED_PAGES = ["dashboard.html", "profile.html", "bookmarks.html", "fan-submissions.html",
  "admin-dashboard.html", "manage-content.html", "manage-users.html", "moderate-submissions.html", "usage-stats.html"];

function fhLoggedIn() { return !!localStorage.getItem("fh_token"); }

function wireAuthNav() {
  const root = window.FH_ROOT || "/";
  const loggedIn = fhLoggedIn();
  const target = root + (loggedIn ? "pages/profile.html" : "pages/login.html");
  document.querySelectorAll('.fh-navbar a[title="Profile"], .fh-tab[data-tab="profile"]').forEach((a) => {
    a.href = target;
    a.title = loggedIn ? "Profile" : "Log in";
  });
  // signed-out-only / signed-in-only blocks (e.g. the "New here?" card)
  document.querySelectorAll("[data-guest-only]").forEach((el) => { el.style.display = loggedIn ? "none" : ""; });
  document.querySelectorAll("[data-user-only]").forEach((el) => { el.style.display = loggedIn ? "" : "none"; });
  // UX only — the backend still enforces the admin role on every admin endpoint
  let isAdmin = false;
  try { isAdmin = JSON.parse(localStorage.getItem("fh_user") || "{}").role === "admin"; } catch (e) {}
  document.querySelectorAll("[data-admin-only]").forEach((el) => { el.style.display = loggedIn && isAdmin ? "" : "none"; });
}

// Login comes first: every page except the sign-in pages needs a session,
// or the "Continue as guest" choice made on the login screen (this tab only).
const PUBLIC_PAGES = ["login.html", "register.html", "forgot-password.html", "reset-password.html"];

function guardProtectedPage() {
  const file = window.location.pathname.split("/").pop() || "index.html";
  if (PUBLIC_PAGES.includes(file) || fhLoggedIn()) return;
  if (!PROTECTED_PAGES.includes(file) && sessionStorage.getItem("fh_guest")) return;
  const rootPath = new URL(window.FH_ROOT, window.location.href).pathname;
  const next = window.location.pathname.replace(rootPath, "") + window.location.search;
  window.location.replace(window.FH_ROOT + "pages/login.html?next=" + encodeURIComponent(next));
}

// ---- Toast notifications ---------------------------------------------------
function fhToast(message, ms = 3500) {
  const el = document.createElement("div");
  el.className = "fh-toast";
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "polite");
  el.textContent = message; // textContent: never inject user names as HTML
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, ms);
}
window.fhToast = fhToast;

// "Welcome back" appears once per browser session, only for signed-in users
function showWelcomeToast() {
  if (!fhLoggedIn() || sessionStorage.getItem("fh_welcomed")) return;
  const file = window.location.pathname.split("/").pop();
  if (file !== "index.html" && file !== "") return;
  let name = "";
  try { name = (JSON.parse(localStorage.getItem("fh_user") || "{}").name || "").split(" ")[0]; } catch (e) {}
  sessionStorage.setItem("fh_welcomed", "1");
  fhToast(name ? `Welcome back, ${name}` : "Welcome back");
}

document.addEventListener("DOMContentLoaded", () => {
  guardProtectedPage();
  showWelcomeToast();
  wireAuthNav();
  initTheme();
  initFontSize();
  wireThemeToggle();
  highlightActiveTab();
});
