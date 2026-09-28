// ==========================================================================
// fonts.js — lets the user pick a font pairing for the whole site.
// Self-contained: applies the saved choice on every page load, and wires
// the picker UI only where it exists (profile.html).
// ==========================================================================

const FONT_OPTIONS = [
  {
    id: "modern",
    label: "Modern (default)",
    display: '"Space Grotesk", "Segoe UI", sans-serif',
    body: '"Inter", "Segoe UI", sans-serif',
    url: null, // already loaded statically in <head> on every page
  },
  {
    id: "storyteller",
    label: "Storyteller (serif)",
    display: '"Fraunces", Georgia, serif',
    body: '"Inter", "Segoe UI", sans-serif',
    url: "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap",
  },
  {
    id: "playful",
    label: "Playful (rounded)",
    display: '"Baloo 2", "Segoe UI", sans-serif',
    body: '"Nunito Sans", "Segoe UI", sans-serif',
    url: "https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;700&family=Nunito+Sans:wght@400;600&display=swap",
  },
  {
    id: "comic",
    label: "Comic Panel",
    display: '"Bangers", "Segoe UI", sans-serif',
    body: '"Inter", "Segoe UI", sans-serif',
    url: "https://fonts.googleapis.com/css2?family=Bangers&family=Inter:wght@400;500;600&display=swap",
  },
  {
    id: "elegant",
    label: "Elegant (display serif)",
    display: '"Playfair Display", Georgia, serif',
    body: '"Source Sans 3", "Segoe UI", sans-serif',
    url: "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Source+Sans+3:wght@400;600&display=swap",
  },
  {
    id: "minimal",
    label: "Minimal Mono",
    display: '"JetBrains Mono", monospace',
    body: '"Inter", "Segoe UI", sans-serif',
    url: "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700&family=Inter:wght@400;500;600&display=swap",
  },
];

function applyFont(id) {
  const option = FONT_OPTIONS.find((f) => f.id === id) || FONT_OPTIONS[0];

  if (option.url) {
    let link = document.getElementById("fh-font-link");
    if (!link) {
      link = document.createElement("link");
      link.id = "fh-font-link";
      link.rel = "stylesheet";
      document.head.appendChild(link);
    }
    link.href = option.url;
  }

  document.documentElement.style.setProperty("--font-display", option.display);
  document.documentElement.style.setProperty("--font-body", option.body);
  localStorage.setItem("fh_font", id);

  const select = document.getElementById("font-picker-select");
  if (select && select.value !== id) select.value = id;
}

function initFontPicker() {
  const saved = localStorage.getItem("fh_font") || "modern";
  applyFont(saved);

  const select = document.getElementById("font-picker-select");
  if (select) {
    select.innerHTML = FONT_OPTIONS.map(
      (f) => `<option value="${f.id}">${f.label}</option>`
    ).join("");
    select.value = saved;
    select.addEventListener("change", () => applyFont(select.value));
  }
}

document.addEventListener("DOMContentLoaded", initFontPicker);
