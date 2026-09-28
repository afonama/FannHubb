// ==========================================================================
// admin.js — Admin Control Panel: overview stats, content/submissions/
// feedback tables, usage stats. Protected routes — the backend verifies the
// admin role (JWT role=admin) on every /admin/* call; a non-admin token
// gets a 403 and these calls fall back to their placeholder data.
// ==========================================================================

async function initAdminOverview() {
  const el = document.getElementById("stat-active-users");
  if (!el) return;
  const stats = await apiGet("/admin/stats", {
    active_users_today: 0, total_content: 0, pending_submissions: 0, chatbot_total_messages: 0,
  });
  document.getElementById("stat-active-users").textContent = stats.active_users_today ?? 0;
  document.getElementById("stat-content-count").textContent = stats.total_content ?? 0;
  document.getElementById("stat-pending").textContent = stats.pending_submissions ?? 0;
  document.getElementById("stat-chatbot-vol").textContent = stats.chatbot_total_messages ?? 0;
}

async function initManageContent() {
  const tbody = document.getElementById("content-table-body");
  if (!tbody) return;
  const data = await apiGet("/admin/content", { items: [] });
  const items = Array.isArray(data) ? data : data.items || [];
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="text-muted-fh">No content yet — add your first item.</td></tr>`;
    return;
  }
  tbody.innerHTML = items
    .map(
      (item) => `
      <tr>
        <td>${esc(item.title)}</td>
        <td>${esc(item.category_name || item.category_slug || "")}</td>
        <td>${esc(item.type)}</td>
        <td>
          <button class="btn-fh-outline btn-sm" data-edit="${item.id}">Edit</button>
          <button class="btn-fh-outline btn-sm" data-delete="${item.id}">Delete</button>
        </td>
      </tr>`
    )
    .join("");

  tbody.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await apiDelete(`/admin/content/${btn.dataset.delete}`, null, { success: true });
      btn.closest("tr").remove();
    });
  });
}

async function initManageUsers() {
  const tbody = document.getElementById("users-table-body");
  if (!tbody) return;
  // Note: this API doesn't currently expose a user-listing endpoint (only
  // /admin/stats.users_by_role, a breakdown by role, not a per-user list),
  // so this table can't be populated live yet — surface that honestly.
  tbody.innerHTML = `<tr><td colspan="4" class="text-muted-fh">User management isn't available in this API version yet (no /admin/users list endpoint) — the backend only reports totals by role via /admin/stats.</td></tr>`;

  const stats = await apiGet("/admin/stats", null);
  if (stats && stats.users_by_role) {
    const summary = document.getElementById("users-by-role-summary");
    if (summary) {
      summary.textContent = Object.entries(stats.users_by_role)
        .map(([role, count]) => `${role}: ${count}`)
        .join(" · ");
    }
  }
}

async function initModerateSubmissions() {
  const list = document.getElementById("submissions-list");
  if (!list) return;
  const data = await apiGet("/admin/submissions", { items: [] }, { status: "pending" });
  const items = Array.isArray(data) ? data : data.items || [];
  if (!items.length) {
    list.innerHTML = `<p class="text-muted-fh">No pending submissions.</p>`;
    return;
  }
  list.innerHTML = items
    .map(
      (s) => `
      <div class="fh-card" style="margin-bottom:0.8rem;" data-submission="${s.id}">
        <p style="font-weight:600; margin-bottom:0.2rem;">${esc(s.title)}</p>
        <p class="text-muted-fh" style="font-size:0.8rem;">by ${esc(s.author_name || s.author_email || "a user")}</p>
        <div class="d-flex gap-sm" style="margin-top:0.5rem;">
          <button class="btn-fh-primary btn-sm" data-approve="${s.id}">Approve</button>
          <button class="btn-fh-outline btn-sm" data-reject="${s.id}">Reject</button>
        </div>
      </div>`
    )
    .join("");

  list.querySelectorAll("[data-approve]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await apiSend(`/admin/submissions/${btn.dataset.approve}`, "PATCH", { status: "approved" }, { success: true });
      btn.closest("[data-submission]").remove();
    })
  );
  list.querySelectorAll("[data-reject]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await apiSend(`/admin/submissions/${btn.dataset.reject}`, "PATCH", { status: "rejected" }, { success: true });
      btn.closest("[data-submission]").remove();
    })
  );
}

async function initUsageStats() {
  const el = document.getElementById("popular-categories-chart");
  if (!el) return;
  const stats = await apiGet("/admin/stats", { popular_categories: [], chatbot_volume: [] });
  el.textContent = (stats.popular_categories || []).map((c) => `${c.name}: ${c.views}`).join(" · ") || "No data yet.";
  const chatEl = document.getElementById("chatbot-volume-chart");
  if (chatEl) {
    chatEl.textContent =
      (stats.chatbot_volume || []).map((d) => `${d.date}: ${d.messages}`).join(" · ") || "No data yet.";
  }
}

// Frontend guard: the backend already returns 403 to non-admins, this just
// gives a clear message (and login link) instead of silently empty tables.
async function requireAdmin() {
  const me = await apiGet("/auth/me", null);
  if (me && me.role === "admin") return true;
  const main = document.querySelector("main.page-content");
  if (main) {
    const root = window.FH_ROOT || "/";
    main.innerHTML = `<div class="fh-card" style="margin-top:1rem;">
      <h2 style="font-size:1.2rem;">Admins only</h2>
      <p class="text-muted-fh">${me ? "Your account doesn't have admin access." : "Log in with an admin account to see this page."}</p>
      <a href="${root}pages/login.html" class="btn-fh-primary">Go to login</a></div>`;
  }
  return false;
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!document.querySelector("[data-admin-page], #stat-active-users, #content-table-body, #users-table-body, #submissions-list, #popular-categories-chart")) return;
  if (!(await requireAdmin())) return;
  initAdminOverview();
  initManageContent();
  initManageUsers();
  initModerateSubmissions();
  initUsageStats();
});
