// ==========================================================================
// content-explorer.js — powers: category.html, content-detail.html,
// character-profiles.html, articles.html, merchandise.html,
// upcoming-releases.html, fan-submissions.html, and the homepage's
// trending/spotlight sections.
//
// Field names below match the live API (ContentListItem / CharacterRead /
// MerchandiseRead): every item has "id" (not content_id/character_id/
// item_id) and "category_slug" (not "category").
// ==========================================================================

const CATEGORY_LABELS = {
  anime: "Anime", gaming: "Gaming", movies: "Movies", "tv-shows": "TV Shows",
  kpop: "K-Pop", comics: "Comics", manga: "Manga", cosplay: "Cosplay",
};

// Each fandom gets its own accent so the feed and explore grid feel colour-
// coded by category rather than one primary colour repeated everywhere.
const CATEGORY_COLOR_VARS = {
  anime: "--cat-anime", gaming: "--cat-gaming", movies: "--cat-movies",
  "tv-shows": "--cat-tv-shows", kpop: "--cat-kpop", comics: "--cat-comics",
  manga: "--cat-manga", cosplay: "--cat-cosplay",
};
function catColor(categorySlug) {
  return `var(${CATEGORY_COLOR_VARS[categorySlug] || "--primary"})`;
}

const FALLBACK_CONTENT = [
  { id: 1, title: "Sample Anime Feature", category_slug: "anime", type: "article", popularity_score: 88 },
  { id: 2, title: "Sample Gaming Trailer", category_slug: "gaming", type: "video", popularity_score: 76 },
  { id: 3, title: "Sample K-Pop Spotlight", category_slug: "kpop", type: "article", popularity_score: 95 },
];

// GET /categories, cached for the lifetime of the page — used wherever we
// need real category ids (the submissions form) rather than just slugs.
let _categoriesCache = null;
async function loadCategories() {
  if (_categoriesCache) return _categoriesCache;
  const data = await apiGet("/categories", []);
  _categoriesCache = Array.isArray(data) ? data : data.items || [];
  return _categoriesCache;
}

function itemsOf(data, fallback) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  return fallback || [];
}

function renderExploreGrid(targetId, items, linkBase = (window.FH_ROOT || "/") + "pages/content-detail.html") {
  const el = document.getElementById(targetId);
  if (!el) return;
  if (!items || items.length === 0) {
    el.innerHTML = `<p class="text-muted-fh">No results found.</p>`;
    return;
  }
  el.innerHTML = items
    .map(
      (item) => `
      <a href="${esc(linkBase)}?id=${esc(item.id)}" class="explore-card fh-card">
        <div class="explore-thumb" style="--cat-color:${catColor(item.category_slug)};"></div>
        <p class="explore-title">${esc(item.title || item.name)}</p>
        <p class="explore-meta">${esc(item.category_name || CATEGORY_LABELS[item.category_slug] || item.category_slug || "")}${item.type ? " · " + esc(item.type) : ""}</p>
      </a>`
    )
    .join("");
}

// Home-feed style: one full-width card per item (media, caption, then a row
// of like / bookmark / share actions), rather than a multi-column grid.
function renderFeedCards(targetId, items) {
  const el = document.getElementById(targetId);
  if (!el) return;
  if (!items || items.length === 0) {
    el.innerHTML = `<p class="text-muted-fh">Nothing trending yet — check back soon.</p>`;
    return;
  }
  const root = window.FH_ROOT || "/";
  el.innerHTML = items
    .map((item) => {
      const id = item.id;
      const label = item.category_name || CATEGORY_LABELS[item.category_slug] || item.category_slug || "";
      return `
      <article class="feed-card">
        <a href="${root}pages/content-detail.html?id=${esc(id)}">
          <div class="feed-card-media" style="--cat-color:${catColor(item.category_slug)};">
            ${label ? `<span class="cat-badge" style="--cat-color:${catColor(item.category_slug)};">${esc(label)}</span>` : ""}
          </div>
        </a>
        <div class="feed-card-body">
          <p class="feed-card-title">${esc(item.title || item.name)}</p>
          <p class="feed-card-desc">${esc(item.type ? item.type[0].toUpperCase() + item.type.slice(1) : "Fan Hub pick")} · trending with the community</p>
        </div>
        <div class="feed-card-actions">
          <button type="button" class="fh-like-btn" data-liked="false" title="Like">🤍</button>
          <button type="button" class="fh-bookmark-btn" data-content-id="${esc(id)}" data-bookmarked="false" title="Bookmark">🔖</button>
          <button type="button" class="fh-share-btn" data-title="${esc(item.title || item.name || "")}" data-id="${esc(id)}" title="Share">↗️</button>
          <span class="spacer"></span>
        </div>
      </article>`;
    })
    .join("");

  el.querySelectorAll(".fh-like-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const liked = btn.dataset.liked === "true";
      btn.dataset.liked = liked ? "false" : "true";
      btn.textContent = liked ? "🤍" : "❤️";
    });
  });
  el.querySelectorAll(".fh-bookmark-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const bookmarked = btn.dataset.bookmarked === "true";
      const id = btn.dataset.contentId;
      if (bookmarked) {
        await apiDelete("/bookmarks", { content_type: "content", content_id: id }, { deleted: true });
      } else {
        await apiSend("/bookmarks", "POST", { content_type: "content", content_id: Number(id) }, { id: Date.now() });
      }
      btn.dataset.bookmarked = bookmarked ? "false" : "true";
      btn.textContent = bookmarked ? "🔖" : "✅";
    });
  });
  el.querySelectorAll(".fh-share-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = `${window.location.origin}${root}pages/content-detail.html?id=${btn.dataset.id}`;
      const title = btn.dataset.title || "Fan Hub Plus";
      if (navigator.share) {
        try { await navigator.share({ title, url }); return; } catch (err) { if (err.name === "AbortError") return; }
      }
      try {
        await navigator.clipboard.writeText(url);
        const original = btn.textContent;
        btn.textContent = "✅";
        setTimeout(() => (btn.textContent = original), 1500);
      } catch (err) { console.warn("Clipboard copy failed", err); }
    });
  });
}

// Rebuild the fandom rail from the real /categories list (slugs + names come
// from the database); the hardcoded rail in index.html stays as the fallback.
const CATEGORY_ICONS = {
  anime: "🎌", gaming: "🎮", movies: "🎬", "tv-shows": "📺",
  kpop: "🎤", comics: "💥", manga: "📖", cosplay: "🎭",
};
async function initFandomRail() {
  const rail = document.getElementById("fandom-rail");
  if (!rail) return;
  const cats = await loadCategories();
  if (!cats.length) return;
  const root = window.FH_ROOT || "/";
  rail.innerHTML = cats
    .map(
      (c) => `
      <a href="${root}pages/categories/category.html?type=${esc(c.slug)}" class="fandom-story">
        <span class="fandom-story-ring" style="--story-color:${catColor(c.slug)};">${CATEGORY_ICONS[c.slug] || "🌟"}</span>${esc(c.name)}
      </a>`
    )
    .join("");
}

// -------------------- Homepage: trending + spotlight --------------------
async function initHomepage() {
  initFandomRail();
  const trendingEl = document.getElementById("trending-grid");
  if (!trendingEl) return;
  loadInto("trending-grid", "/content", { sort: "popular", page_size: 10 }, (items) => renderFeedCards("trending-grid", items));
}

// -------------------- Category explorer page --------------------
async function initCategoryPage() {
  const grid = document.getElementById("category-results");
  if (!grid) return;

  const params = new URLSearchParams(window.location.search);
  const type = params.get("type") || "";
  const titleEl = document.getElementById("category-title");
  const crumbEl = document.getElementById("breadcrumb-category");
  if (titleEl) titleEl.textContent = type ? CATEGORY_LABELS[type] || type : "Explore all";
  if (crumbEl) crumbEl.textContent = type ? CATEGORY_LABELS[type] || type : "Explore";

  async function runQuery() {
    const q = document.getElementById("filter-search")?.value || "";
    const genre = document.getElementById("filter-genre")?.value || "";
    const year = document.getElementById("filter-year")?.value || "";
    const contentType = document.getElementById("filter-type")?.value || "";
    const sort = document.getElementById("filter-sort")?.value || "latest";

    loadInto("category-results", "/content", { category: type, q, genre, year, type: contentType, sort },
      (items) => renderExploreGrid("category-results", items));
  }

  ["filter-search", "filter-genre", "filter-year", "filter-type", "filter-sort"].forEach((id) => {
    const field = document.getElementById(id);
    if (field) field.addEventListener("input", runQuery);
  });

  runQuery();
}

// -------------------- Content detail page --------------------
async function initContentDetail() {
  const titleEl = document.getElementById("content-title");
  if (!titleEl) return;

  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");

  const data = await apiGet(`/content/${encodeURIComponent(id)}`, null);
  if (!data) {
    titleEl.textContent = "Couldn't load this content";
    showError(document.getElementById("content-description"), () => window.location.reload());
    return;
  }

  titleEl.textContent = data.title;
  document.getElementById("content-meta").textContent =
    `${data.category_name || CATEGORY_LABELS[data.category_slug] || data.category_slug} · ${data.type} · Released ${data.release_date || "—"}`;
  document.getElementById("content-description").textContent = data.body_rich_text || data.description || "";

  const catLink = document.getElementById("breadcrumb-cat-link");
  if (catLink) catLink.href = `${window.FH_ROOT || "/"}pages/categories/category.html?type=${data.category_slug}`;

  const related = await apiGet("/content", null, { category: data.category_slug });
  const relatedItems = itemsOf(related, []).filter((c) => String(c.id) !== String(id));
  renderExploreGrid("related-grid", relatedItems);

  // Bookmark / rating widgets on this page get the real state from the API
  // (content-detail includes `bookmarked` + `user_rating` when a JWT is sent).
  const bookmarkBtn = document.getElementById("bookmark-toggle");
  if (bookmarkBtn) {
    bookmarkBtn.dataset.contentId = id;
    bookmarkBtn.dataset.bookmarked = data.bookmarked ? "true" : "false";
    bookmarkBtn.textContent = data.bookmarked ? "✅ Bookmarked" : "🔖 Bookmark";
  }
  const rateBtn = document.getElementById("rate-up");
  const rateCount = document.getElementById("rate-count");
  if (rateBtn) rateBtn.dataset.contentId = id;
  if (rateCount && data.rating) rateCount.textContent = data.rating.thumbs_up ?? 0;
  if (rateBtn && data.user_rating) { rateBtn.disabled = true; rateBtn.style.opacity = "0.6"; }
}

// -------------------- Character profiles page --------------------
async function initCharacterProfiles() {
  const grid = document.getElementById("character-grid");
  if (!grid) return;

  async function loadCharacters(category = "") {
    loadInto("character-grid", "/characters", { category },
      (items) => renderExploreGrid("character-grid", items, pageUrl("character-detail.html")));
  }

  document.querySelectorAll("#character-filter-chips .chip").forEach((chip) => {
    chip.addEventListener("click", (e) => {
      e.preventDefault();
      loadCharacters(chip.dataset.cat);
    });
  });

  loadCharacters();
}

// -------------------- Articles page --------------------
// There's no dedicated /articles endpoint — articles are just content items
// with type=article, so this filters /content the same way category.html does.
async function initArticles() {
  const feed = document.getElementById("articles-feed");
  if (!feed) return;
  loadInto("articles-feed", "/content", { type: "article", sort: "latest" }, (items) => {
    if (!items.length) { feed.innerHTML = `<p class="text-muted-fh">No articles yet.</p>`; return; }
    feed.innerHTML = items
      .map(
        (a) => `
        <article class="fh-card" style="margin-bottom:1.2rem;">
          <div class="explore-thumb" style="aspect-ratio:16/9; margin-bottom:0.8rem; --cat-color:${catColor(a.category_slug)};"></div>
          <h2 style="font-size:1.15rem; margin-bottom:0.3rem;">${esc(a.title)}</h2>
          <p class="text-muted-fh" style="font-size:0.8rem; margin-bottom:0.6rem;">${esc(a.category_name || CATEGORY_LABELS[a.category_slug] || a.category_slug)} · ${esc(a.release_date || "")}</p>
          <a href="${(window.FH_ROOT || "/")}pages/content-detail.html?id=${esc(a.id)}">Read more →</a>
        </article>`
      )
      .join("");
  });
}

// -------------------- Merchandise page --------------------
async function initMerchandise() {
  const grid = document.getElementById("merch-grid");
  if (!grid) return;

  async function loadMerch() {
    const category = document.getElementById("merch-category")?.value || "";
    const tag = document.getElementById("merch-tag")?.value || "";
    loadInto("merch-grid", "/merchandise", { category, tag },
      (items) => renderExploreGrid("merch-grid", items, pageUrl("merchandise-detail.html")));
  }

  ["merch-category", "merch-tag"].forEach((id) => {
    const field = document.getElementById(id);
    if (field) field.addEventListener("change", loadMerch);
  });

  loadMerch();
}

// -------------------- Upcoming releases page --------------------
async function initUpcoming() {
  const grid = document.getElementById("upcoming-grid");
  if (!grid) return;
  loadInto("upcoming-grid", "/merchandise", { upcoming: true },
    (items) => renderExploreGrid("upcoming-grid", items, pageUrl("merchandise-detail.html")));
}

// -------------------- Fan submissions page --------------------
// POST /submissions wants a real integer category_id (not a slug), so the
// dropdown is populated from GET /categories rather than the local label map.
async function initFanSubmissions() {
  const form = document.getElementById("submission-form");
  if (!form) return;

  const categorySelect = document.getElementById("sub-category");
  const categories = await loadCategories();
  const source = categories.length
    ? categories.map((c) => [c.id, c.name])
    : Object.entries(CATEGORY_LABELS); // fallback if the API isn't reachable
  source.forEach(([value, label]) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    categorySelect.appendChild(opt);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = document.getElementById("sub-title").value;
    const category_id = Number(categorySelect.value) || undefined;
    const body = document.getElementById("sub-body").value;

    const result = await apiSend("/submissions", "POST", { title, body, category_id }, { status: "pending" });
    if (result) {
      document.getElementById("submission-success").style.display = "block";
      form.reset();
    }
  });
}

// -------------------- Character / merchandise detail pages --------------------
async function initEntityDetail() {
  const kind = document.body.dataset.detail;
  if (!kind) return;
  const isChar = kind === "character";
  const path = isChar ? "/characters" : "/merchandise";
  const id = new URLSearchParams(window.location.search).get("id");
  const titleEl = document.getElementById("content-title");
  const body = document.getElementById("content-description");
  showLoading(body);
  const data = await apiGet(`${path}/${encodeURIComponent(id)}`, null);
  if (!data) {
    titleEl.textContent = "Couldn't load this page";
    showError(body, () => window.location.reload());
    return;
  }
  titleEl.textContent = data.name;
  document.title = data.name + " — Fan Hub Plus";
  const bits = [data.category_name, data.tag, data.is_upcoming ? "Upcoming" : "", data.release_date ? "Releases " + data.release_date : ""];
  document.getElementById("content-meta").textContent = bits.filter(Boolean).join(" · ");
  body.textContent = data.bio || data.description || "";
  const img = document.getElementById("detail-image");
  if (img && data.image_url) img.style.backgroundImage = "url(" + JSON.stringify(safeUrl(data.image_url)) + ")";
  const btn = document.getElementById("bookmark-toggle");
  if (btn) { btn.dataset.contentId = id; btn.dataset.contentType = isChar ? "character" : "merchandise"; }
}

document.addEventListener("DOMContentLoaded", () => {
  initEntityDetail();
  initHomepage();
  initCategoryPage();
  initContentDetail();
  initCharacterProfiles();
  initArticles();
  initMerchandise();
  initUpcoming();
  initFanSubmissions();
});
