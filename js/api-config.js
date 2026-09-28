// ==========================================================================
// api-config.js — single place to point every JS file at the backend.
// Matches the Fan Hub Plus FastAPI backend (OpenAPI 3.1, prefix /api/v1).
// ==========================================================================

const API_BASE = "https://fannhubb.onrender.com/api/v1";

/** Builds a query string from an object, skipping null/undefined/"" values. */
function qs(params) {
  if (!params) return "";
  const parts = Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
  return parts.length ? "?" + parts.join("&") : "";
}

// Shared in-flight refresh so parallel 401s only rotate the refresh token once
// (the API revokes the old refresh token on every use).
let _refreshPromise = null;
async function refreshAccessToken() {
  const refresh = localStorage.getItem("fh_refresh_token");
  if (!refresh) return false;
  if (!_refreshPromise) {
    _refreshPromise = (async () => {
      try {
        const res = await fetch(API_BASE + "/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        if (!res.ok) throw new Error("refresh failed " + res.status);
        const t = await res.json();
        localStorage.setItem("fh_token", t.access_token);
        localStorage.setItem("fh_refresh_token", t.refresh_token);
        return true;
      } catch (err) {
        localStorage.removeItem("fh_token");
        localStorage.removeItem("fh_refresh_token");
        localStorage.removeItem("fh_user");
        return false;
      } finally {
        setTimeout(() => { _refreshPromise = null; }, 0);
      }
    })();
  }
  return _refreshPromise;
}

/** fetch with auth headers; on a 401 refresh the token once and retry. */
async function authFetch(url, init = {}, extraHeaders = {}) {
  const build = () => ({ ...init, headers: authHeaders(extraHeaders) });
  let res = await fetch(url, build());
  if (res.status === 401 && !url.includes("/auth/") && (await refreshAccessToken())) {
    res = await fetch(url, build());
  }
  return res;
}

function authHeaders(extra = {}) {
  const token = localStorage.getItem("fh_token") || "";
  return token ? { Authorization: "Bearer " + token, ...extra } : { ...extra };
}

/**
 * GET wrapped with a JSON parse + safe fallback so a page never breaks just
 * because the backend isn't running yet or an endpoint 404s.
 * @param {string} path - path relative to API_BASE, e.g. "/content"
 * @param {object} fallback - value returned if the request fails
 * @param {object} params - optional query params object
 */
async function apiGet(path, fallback = null, params = null) {
  try {
    const res = await authFetch(API_BASE + path + qs(params));
    if (!res.ok) throw new Error("Request failed: " + res.status);
    return await res.json();
  } catch (err) {
    console.warn(`API not available yet for ${path}, using fallback data.`, err);
    return fallback;
  }
}

/** POST / PATCH / PUT with a JSON body. */
async function apiSend(path, method, body, fallback = null) {
  try {
    const res = await authFetch(API_BASE + path, { method, body: JSON.stringify(body) }, { "Content-Type": "application/json" });
    if (!res.ok) throw new Error("Request failed: " + res.status);
    if (res.status === 204) return true;
    return await res.json();
  } catch (err) {
    console.warn(`API not available yet for ${path}, using fallback response.`, err);
    return fallback;
  }
}

/** DELETE — optionally with query params (the API uses these for /bookmarks). */
async function apiDelete(path, params = null, fallback = null) {
  try {
    const res = await authFetch(API_BASE + path + qs(params), { method: "DELETE" });
    if (!res.ok) throw new Error("Request failed: " + res.status);
    if (res.status === 204) return true;
    return await res.json();
  } catch (err) {
    console.warn(`API not available yet for ${path}, using fallback response.`, err);
    return fallback;
  }
}

/** multipart/form-data upload (avatar). Do not set Content-Type manually —
    the browser needs to add its own boundary. */
async function apiUpload(path, file, fallback = null) {
  try {
    const form = new FormData();
    form.append("file", file);
    const res = await authFetch(API_BASE + path, { method: "POST", body: form });
    if (!res.ok) throw new Error("Request failed: " + res.status);
    return await res.json();
  } catch (err) {
    console.warn(`Upload failed for ${path}.`, err);
    return fallback;
  }
}

// ---------------------------------------------------------------------------
// Shared helpers: escaping, safe URLs, detail-page links, loading/error UI
// ---------------------------------------------------------------------------
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function safeUrl(u) {
  try { const x = new URL(u, window.location.href); return ["http:", "https:"].includes(x.protocol) ? x.href : "#"; }
  catch { return "#"; }
}
function pageUrl(name) { return (window.FH_ROOT || "/") + "pages/" + name; }
function detailHref(type, id) {
  const page = type === "character" ? "character-detail.html" : type === "merchandise" ? "merchandise-detail.html" : "content-detail.html";
  return pageUrl(page) + "?id=" + encodeURIComponent(id);
}
function showLoading(el) {
  if (!el) return;
  el.innerHTML = '<div class="fh-spinner" role="status" aria-label="Loading"></div><p class="text-muted-fh fh-load-hint" style="grid-column:1/-1;text-align:center;font-size:0.8rem;display:none;">Waking the server up — the first load can take a moment…</p>';
  setTimeout(() => { const h = el.querySelector(".fh-load-hint"); if (h) h.style.display = "block"; }, 4000);
}
function showError(el, retry, msg) {
  if (!el) return;
  el.innerHTML = '<div class="fh-card" style="grid-column:1/-1;text-align:center;"><p style="margin:0 0 0.6rem;font-weight:600;">' + esc(msg || "Couldn't load this right now.") + '</p><button type="button" class="btn-fh-outline fh-retry">Try again</button></div>';
  const b = el.querySelector(".fh-retry");
  if (b && retry) b.addEventListener("click", retry);
}
/** Shows a spinner, fetches, then renders — or shows an error with a retry button. */
async function loadInto(id, path, params, render) {
  const el = document.getElementById(id);
  if (!el) return;
  showLoading(el);
  const data = await apiGet(path, null, params);
  if (data === null) return showError(el, () => loadInto(id, path, params, render));
  render(Array.isArray(data) ? data : data.items || []);
}
