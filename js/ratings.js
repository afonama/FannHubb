// ==========================================================================
// ratings.js — thumbs-up / star rating on content
// API: POST /content/{content_id}/rate  { scale: "thumbs"|"stars", value }
//      -> { rating, summary: { average, count, thumbs_up, thumbs_down, ... }, created }
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  const rateButtons = [
    document.getElementById("rate-up"),
    document.getElementById("media-rate-up"),
  ].filter(Boolean);

  rateButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.contentId || new URLSearchParams(window.location.search).get("id");
      const result = await apiSend(`/content/${id}/rate`, "POST", { scale: "thumbs", value: 1 }, null);

      const countEl = document.getElementById("rate-count");
      if (result && result.summary) {
        if (countEl) countEl.textContent = result.summary.thumbs_up;
      } else if (countEl) {
        countEl.textContent = (parseInt(countEl.textContent, 10) || 0) + 1;
        console.warn("Rating not saved to backend yet — reflected locally only.");
      }

      btn.disabled = true;
      btn.style.opacity = "0.6";
    });
  });

  // Optional 5-star widget, if the page has one (data-star-value 1..5 on each star).
  const starWidget = document.getElementById("star-rating");
  if (starWidget) {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("id");
    starWidget.querySelectorAll("[data-star-value]").forEach((star) => {
      star.addEventListener("click", async () => {
        const value = Number(star.dataset.starValue);
        const result = await apiSend(`/content/${id}/rate`, "POST", { scale: "stars", value }, null);
        starWidget.querySelectorAll("[data-star-value]").forEach((s) => {
          s.classList.toggle("active", Number(s.dataset.starValue) <= value);
        });
        const avgEl = document.getElementById("star-rating-average");
        if (avgEl && result && result.summary) {
          avgEl.textContent = result.summary.average.toFixed(1);
        }
      });
    });
  }
});
