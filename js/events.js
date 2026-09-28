// ==========================================================================
// events.js — Location-Aware Event Discovery and Calendar
// API: GET /events?city=&near=lat,lng&radius_km=&category=&upcoming_only=
//      -> { items: [{ id, name, city, lat, lng, start_date, end_date,
//                      ticket_url, description, category_slug, distance_km }] }
// ==========================================================================

const FALLBACK_EVENTS = [
  { id: 1, name: "Sample Anime Con", start_date: "2026-11-14", city: "Lagos", ticket_url: "#" },
  { id: 2, name: "Sample Gaming Meetup", start_date: "2026-10-02", city: "Abuja", ticket_url: "#" },
];

let _nearCoords = null;

function renderEvents(events) {
  const list = document.getElementById("events-list");
  if (!list) return;
  if (!events || events.length === 0) {
    list.innerHTML = `<p class="text-muted-fh">No events found for this filter.</p>`;
    return;
  }
  list.innerHTML = events
    .map(
      (ev) => `
      <div class="fh-card" style="margin-bottom:0.8rem; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
        <div>
          <p style="font-weight:600; margin-bottom:0.15rem;">${esc(ev.name)}</p>
          <p class="text-muted-fh" style="font-size:0.8rem; margin-bottom:0;">
            ${esc(ev.start_date)}${ev.end_date && ev.end_date !== ev.start_date ? " – " + esc(ev.end_date) : ""} · ${esc(ev.city)}
            ${typeof ev.distance_km === "number" ? ` · ${ev.distance_km.toFixed(0)} km away` : ""}
          </p>
        </div>
        ${ev.ticket_url ? `<a href="${esc(safeUrl(ev.ticket_url))}" class="btn-fh-outline" target="_blank" rel="noopener">Ticket info</a>` : ""}
      </div>`
    )
    .join("");
}

async function loadEvents() {
  const city = document.getElementById("event-city-filter")?.value || "";
  const upcomingOnly = document.getElementById("event-upcoming-only")?.checked ?? true;
  const list = document.getElementById("events-list");
  showLoading(list);
  const data = await apiGet("/events", null, {
    city,
    upcoming_only: upcomingOnly,
    near: _nearCoords,
    radius_km: _nearCoords ? 50 : null,
  });
  if (data === null) return showError(list, loadEvents);
  renderEvents(Array.isArray(data) ? data : data.items || []);
}

document.addEventListener("DOMContentLoaded", () => {
  if (!document.getElementById("events-list")) return;

  loadEvents();

  document.getElementById("event-city-filter")?.addEventListener("input", loadEvents);
  document.getElementById("event-upcoming-only")?.addEventListener("change", loadEvents);

  // GPS-based nearby events, when the user grants location access
  const mapEl = document.getElementById("event-map");
  if (mapEl && navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        _nearCoords = `${pos.coords.latitude},${pos.coords.longitude}`;
        mapEl.textContent = "Showing events near your location (within 50 km).";
        loadEvents();
      },
      () => {
        mapEl.textContent = "Location access denied — showing all events instead.";
      }
    );
  }
});
