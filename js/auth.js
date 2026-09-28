// ==========================================================================
// auth.js — login, register, forgot password
// Matches POST /auth/login, /auth/register (return a TokenPair: access_token
// + refresh_token + role, but no user object), so after either call we
// fetch GET /auth/me separately to get the profile to store locally.
// ==========================================================================

function showError(el, message) {
  el.textContent = message;
  el.style.display = "block";
}

async function storeSessionAndRedirect(tokens) {
  localStorage.setItem("fh_token", tokens.access_token);
  localStorage.setItem("fh_refresh_token", tokens.refresh_token || "");
  sessionStorage.removeItem("fh_welcomed");
  const me = await apiGet("/auth/me", null);
  if (me) localStorage.setItem("fh_user", JSON.stringify(me));
  const next = new URLSearchParams(window.location.search).get("next");
  const safe = next && /^[\w\-\/.]+\.html(\?[\w\-=&%.]*)?$/.test(next) && !next.startsWith("/") && !next.includes("..");
  window.location.href = (window.FH_ROOT || "/") + (safe ? next : me && me.role === "admin" ? "pages/admin/admin-dashboard.html" : "index.html");
}

document.addEventListener("DOMContentLoaded", () => {
  // ---- Login ----
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = document.getElementById("login-email").value;
      const password = document.getElementById("login-password").value;
      const errorEl = document.getElementById("login-error");

      const result = await apiSend("/auth/login", "POST", { email, password }, null);
      if (result && result.access_token) {
        await storeSessionAndRedirect(result);
      } else {
        showError(errorEl, "Couldn't log in — check your email and password.");
      }
    });
  }

  // ---- Register ----
  const registerForm = document.getElementById("register-form");
  if (registerForm) {
    registerForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("reg-name").value;
      const email = document.getElementById("reg-email").value;
      const password = document.getElementById("reg-password").value;
      const confirm = document.getElementById("reg-confirm").value;
      const errorEl = document.getElementById("register-error");

      if (password !== confirm) {
        showError(errorEl, "Passwords don't match.");
        return;
      }

      // checkbox values are expected to be category slugs (anime, gaming, ...)
      const favoriteCategories = Array.from(
        registerForm.querySelectorAll('input[type="checkbox"]:checked')
      ).map((cb) => cb.value);

      const result = await apiSend(
        "/auth/register",
        "POST",
        { name, email, password, favorite_categories: favoriteCategories },
        null
      );

      if (result && result.access_token) {
        await storeSessionAndRedirect(result);
      } else {
        showError(errorEl, "Couldn't create your account — that email might already be in use.");
      }
    });
  }

  // ---- Forgot password ----
  const forgotForm = document.getElementById("forgot-form");
  if (forgotForm) {
    forgotForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = document.getElementById("forgot-email").value;
      // Always returns 200 with an identical message, regardless of whether
      // the address exists — that's the API's design, not a bug here.
      await apiSend("/auth/forgot-password", "POST", { email }, { success: true });
      document.getElementById("forgot-success").style.display = "block";
      forgotForm.querySelector("button[type=submit]").disabled = true;
    });
  }
});

// ---- Logout (called from navbar / profile page) ----
async function fhLogout() {
  const refreshToken = localStorage.getItem("fh_refresh_token") || "";
  await apiSend("/auth/logout", "POST", { refresh_token: refreshToken }, null);
  localStorage.removeItem("fh_token");
  localStorage.removeItem("fh_refresh_token");
  localStorage.removeItem("fh_user");
  sessionStorage.removeItem("fh_welcomed");
  window.location.href = (window.FH_ROOT || "/") + "pages/login.html";
}
