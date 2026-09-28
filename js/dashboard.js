// ==========================================================================
// dashboard.js — greeting, stats, recent activity, bookmarks preview
// API: GET /users/me/dashboard -> DashboardResponse (registered users only;
// visitors get a 401 from this endpoint, so the fallback below covers that).
// ==========================================================================

const FALLBACK_DASHBOARD = {
  greeting: "Hey there 👋",
  stats: { total_bookmarks: 0, total_ratings: 0, total_submissions: 0, pending_submissions: 0, favorite_fandom_count: 0 },
  recent_activity: [],
  favorite_fandoms: [],
  recommended_content: [],
  bookmarks_preview: [],
};

function renderActivity(items) {
  const el = document.getElementById("recent-activity-list");
  if (!el) return;
  if (!items || items.length === 0) {
    el.innerHTML = `<p class="text-muted-fh" style="margin:0;">No recent activity yet — go explore a category to get started.</p>`;
    return;
  }
  el.innerHTML = items
    .map(
      (item) => `
      <div style="padding:0.5rem 0; border-bottom:1px solid var(--border);">
        <strong>${esc(item.label)}</strong>
        <span class="text-muted-fh" style="font-size:0.8rem;"> — ${esc(item.kind)}</span>
      </div>`
    )
    .join("");
}

function renderBookmarksGrid(targetId, items) {
  const el = document.getElementById(targetId);
  if (!el) return;
  if (!items || items.length === 0) {
    el.innerHTML = `<p class="text-muted-fh">No bookmarks yet.</p>`;
    return;
  }
  const root = window.FH_ROOT || "/";
  el.innerHTML = items
    .map(
      (item) => `
      <a href="${esc(detailHref(item.content_type, item.content_id))}" class="explore-card fh-card">
        <div class="explore-thumb" style="--cat-color:var(--primary);"></div>
        <p class="explore-title">${esc(item.title)}</p>
      </a>`
    )
    .join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!document.getElementById("dashboard-greeting") && !document.getElementById("stat-bookmarks")) return;

  showLoading(document.getElementById("recent-activity-list"));
  const data = await apiGet("/users/me/dashboard", null);
  if (!data) {
    showError(document.getElementById("recent-activity-list"), () => window.location.reload(), "Couldn't load your dashboard.");
    return;
  }

  const greetingEl = document.getElementById("dashboard-greeting");
  if (greetingEl && data.greeting) greetingEl.textContent = data.greeting;

  const stats = data.stats || FALLBACK_DASHBOARD.stats;
  const setStat = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? 0; };
  setStat("stat-bookmarks", stats.total_bookmarks);
  setStat("stat-fandoms", stats.favorite_fandom_count);
  setStat("stat-activity", (data.recent_activity || []).length);
  setStat("stat-submissions", stats.total_submissions);

  renderActivity(data.recent_activity);
  renderBookmarksGrid("dashboard-bookmarks-grid", data.bookmarks_preview);
  if (typeof renderExploreGrid === "function" && document.getElementById("dashboard-recommended-grid")) {
    renderExploreGrid("dashboard-recommended-grid", data.recommended_content);
  }
});
