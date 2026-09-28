// ==========================================================================
// feedback.js — feedback form submission
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("feedback-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const type = document.getElementById("feedback-type").value;
    const message = document.getElementById("feedback-message").value;
    const contact_email = document.getElementById("feedback-email")?.value || undefined;

    // API requires message length 10-4000 chars — surface that instead of a
    // silent failure so the user knows why the request didn't go through.
    const errorEl = document.getElementById("feedback-error");
    if (message.trim().length < 10) {
      if (errorEl) { errorEl.textContent = "Please write at least 10 characters."; errorEl.style.display = "block"; }
      return;
    }
    if (errorEl) errorEl.style.display = "none";

    await apiSend("/feedback", "POST", { type, message, contact_email }, { id: Date.now(), status: "open" });

    document.getElementById("feedback-success").style.display = "block";
    form.reset();
  });
});
