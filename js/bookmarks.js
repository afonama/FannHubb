// ==========================================================================
// bookmarks.js — bookmark toggle button + full bookmarks page
// API: POST /bookmarks {content_type, content_id, note}
//      DELETE /bookmarks?content_type=&content_id=  (query params, not path)
//      GET /bookmarks -> {items: [...]}
// ==========================================================================

// Round icon-only buttons (media player) show state with a highlight; the
// wider text buttons on detail pages keep their label.
function setBookmarkState(btn, on) {
  if (btn.id === "media-bookmark") {
    btn.classList.toggle("is-active", on);
    btn.setAttribute("aria-pressed", String(on));
    btn.title = on ? "Bookmarked" : "Bookmark";
  } else {
    btn.textContent = on ? "✅ Bookmarked" : "🔖 Bookmark";
  }
}

async function toggleBookmark(contentId, btn, contentType = "content") {
  if (!contentId) return;
  const isBookmarked = btn.dataset.bookmarked === "true";
  if (isBookmarked) {
    await apiDelete("/bookmarks", { content_type: contentType, content_id: contentId }, { deleted: true });
    btn.dataset.bookmarked = "false";
    setBookmarkState(btn, false);
  } else {
    await apiSend("/bookmarks", "POST", { content_type: contentType, content_id: Number(contentId) }, { id: Date.now() });
    btn.dataset.bookmarked = "true";
    setBookmarkState(btn, true);
  }
}

async function loadBookmarksPage() {
  const grid = document.getElementById("bookmarks-grid");
  if (!grid) return;

  grid.style.display = "";
  showLoading(grid);
  const data = await apiGet("/bookmarks", null);
  if (data === null) return showError(grid, loadBookmarksPage);
  const items = Array.isArray(data) ? data : data.items || [];

  if (!items || items.length === 0) {
    grid.style.display = "none";
    const empty = document.getElementById("bookmarks-empty");
    if (empty) empty.style.display = "block";
    return;
  }

  const root = window.FH_ROOT || "/";
  grid.innerHTML = items
    .map(
      (b) => `
      <a href="${esc(detailHref(b.content_type, b.content_id))}" class="explore-card fh-card">
        <div class="explore-thumb" style="--cat-color:var(--primary);"></div>
        <p class="explore-title">${esc(b.title || "Saved item")}</p>
        ${b.category_slug ? `<p class="explore-meta">${esc(b.category_slug)}</p>` : ""}
        ${b.note ? `<p class="explore-meta">📝 ${esc(b.note)}</p>` : ""}
      </a>`
    )
    .join("");
}

document.addEventListener("DOMContentLoaded", () => {
  const bookmarkButtons = [
    document.getElementById("bookmark-toggle"),
    document.getElementById("media-bookmark"),
  ].filter(Boolean);

  bookmarkButtons.forEach((btn) => {
    btn.dataset.bookmarked = "false";
    btn.addEventListener("click", () => {
      const id = btn.dataset.contentId || new URLSearchParams(window.location.search).get("id");
      toggleBookmark(id, btn, btn.dataset.contentType || "content");
    });
  });

  loadBookmarksPage();
});
