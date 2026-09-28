// ==========================================================================
// profile.js — load + save profile, avatar preview, font-size preference
// API: GET/PATCH /users/me            -> { name, email, avatar_url, ... }
//      GET/PATCH /users/me/preferences -> { favorite_categories, display_prefs }
//      POST /users/me/avatar (multipart) -> { avatar_url }
// ==========================================================================

document.addEventListener("DOMContentLoaded", async () => {
  const nameInput = document.getElementById("profile-name");
  const emailInput = document.getElementById("profile-email");
  if (!nameInput && !emailInput) return;

  const [user, prefs] = await Promise.all([
    apiGet("/users/me", { name: "", email: "", avatar_url: "" }),
    apiGet("/users/me/preferences", { favorite_categories: [] }),
  ]);

  if (nameInput) nameInput.value = user.name || "";
  if (emailInput) emailInput.value = user.email || "";

  const preview = document.getElementById("avatar-preview");
  if (preview && user.avatar_url) {
    preview.style.backgroundImage = `url(${user.avatar_url})`;
    preview.style.backgroundSize = "cover";
    preview.style.backgroundPosition = "center";
  }

  (prefs.favorite_categories || []).forEach((slug) => {
    const cb = document.querySelector(`#profile-form input[value="${slug}"]`);
    if (cb) cb.checked = true;
  });

  // Avatar preview on file select
  const avatarInput = document.getElementById("avatar-upload");
  if (avatarInput) {
    avatarInput.addEventListener("change", () => {
      const file = avatarInput.files[0];
      if (!file || !preview) return;
      preview.style.backgroundImage = `url(${URL.createObjectURL(file)})`;
      preview.style.backgroundSize = "cover";
      preview.style.backgroundPosition = "center";
    });
  }

  // Font size select reflects saved preference
  const fontSizeSelect = document.getElementById("profile-fontsize");
  if (fontSizeSelect) {
    fontSizeSelect.value = localStorage.getItem("fh_font_size") || "16";
    fontSizeSelect.addEventListener("change", () => {
      applyFontSize(fontSizeSelect.value);
    });
  }

  // Save profile
  const form = document.getElementById("profile-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const favoriteCategories = Array.from(
        form.querySelectorAll('input[type="checkbox"]:checked')
      ).map((cb) => cb.value);

      if (avatarInput && avatarInput.files[0]) {
        const result = await apiUpload("/users/me/avatar", avatarInput.files[0], null);
        if (result && result.avatar_url) {
          await apiSend("/users/me", "PATCH", { avatar_url: result.avatar_url }, null);
        }
      }

      await apiSend("/users/me", "PATCH", { name: nameInput.value }, { success: true });
      await apiSend("/users/me/preferences", "PATCH", { favorite_categories: favoriteCategories }, { success: true });

      const updatedUser = await apiGet("/auth/me", null);
      if (updatedUser) localStorage.setItem("fh_user", JSON.stringify(updatedUser));

      document.getElementById("profile-saved").style.display = "block";
    });
  }
});
