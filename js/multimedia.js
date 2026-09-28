// ==========================================================================
// multimedia.js — Interactive Multimedia Center: media player + grid
// There's no dedicated /media endpoint — this reuses /content (which has a
// media_url field per item) filtered by content type, same as everywhere
// else video/audio/image content shows up.
// ==========================================================================

const FALLBACK_MEDIA = [
  { id: 1, title: "Sample Trailer", type: "video", category_slug: "movies" },
  { id: 2, title: "Sample OST Clip", type: "video", category_slug: "anime" },
  { id: 3, title: "Sample Explainer", type: "video", category_slug: "gaming" },
];

async function loadMediaGrid(type = "") {
  const grid = document.getElementById("media-grid");
  if (!grid) return;
  showLoading(grid);
  const data = await apiGet("/content", null, { type: type || null, sort: "latest" });
  if (data === null) return showError(grid, () => loadMediaGrid(type));
  const items = Array.isArray(data) ? data : data.items || [];
  grid.innerHTML = items
    .map(
      (m) => `
      <div class="explore-card fh-card" data-media-id="${esc(m.id)}" data-media-url="${esc(m.media_url || "")}" style="cursor:pointer;">
        <div class="explore-thumb" style="--cat-color:var(--primary);"></div>
        <p class="explore-title">${esc(m.title)}</p>
        <p class="explore-meta">${esc(m.type)}</p>
      </div>`
    )
    .join("");

  grid.querySelectorAll("[data-media-id]").forEach((card) => {
    card.addEventListener("click", () => {
      const caption = document.getElementById("media-caption");
      if (caption) caption.textContent = card.querySelector(".explore-title").textContent;
      const player = document.getElementById("media-player");
      if (player && card.dataset.mediaUrl) player.src = safeUrl(card.dataset.mediaUrl);
      const bookmarkBtn = document.getElementById("media-bookmark");
      if (bookmarkBtn) bookmarkBtn.dataset.contentId = card.dataset.mediaId;
      const rateBtn = document.getElementById("media-rate-up");
      if (rateBtn) rateBtn.dataset.contentId = card.dataset.mediaId;
    });
  });
}

const TYPE_ICONS = { video: "🎬", audio: "🎧", image: "🖼️", article: "📰", trailer: "🍿", explainer: "✨" };

// Build the filter chips from the content types that actually exist in the
// API instead of guessing them.
async function buildTypeChips() {
  const first = document.querySelector('.chip[data-type]');
  if (!first) return;
  const container = first.parentElement;
  const data = await apiGet("/content", null, { page_size: 100 });
  const items = data && Array.isArray(data.items) ? data.items : [];
  const types = [...new Set(items.map((i) => i.type).filter(Boolean))];
  if (!types.length) return; // API unreachable: keep the static chips
  container.innerHTML = types
    .map((t) => `<a href="#" class="chip" data-type="${t}"><span class="chip-icon">${TYPE_ICONS[t] || "🎞️"}</span>${t[0].toUpperCase() + t.slice(1)}</a>`)
    .join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!document.getElementById("media-grid")) return;

  await buildTypeChips();
  loadMediaGrid();

  document.querySelectorAll('[data-type]').forEach((chip) => {
    chip.addEventListener("click", (e) => {
      e.preventDefault();
      loadMediaGrid(chip.dataset.type);
    });
  });
});
