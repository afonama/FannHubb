// ==========================================================================
// notes.js — lets a user attach a short personal note to a bookmarked item
// The API has no PATCH-just-the-note endpoint — a bookmark's note can only
// be set when the bookmark is created (POST /bookmarks {note}). Duplicate
// POSTs are rejected (409), so updating a note means delete-then-recreate.
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  const noteBtn = document.getElementById("add-note-btn");
  const preview = document.getElementById("note-preview");
  if (!noteBtn) return;

  noteBtn.addEventListener("click", async () => {
    const existing = preview.dataset.note || "";
    const note = window.prompt("Add a note to this bookmark:", existing);
    if (note === null) return; // cancelled

    const params = new URLSearchParams(window.location.search);
    const id = Number(params.get("id"));
    const contentType = "content";

    await apiDelete("/bookmarks", { content_type: contentType, content_id: id }, null);
    await apiSend("/bookmarks", "POST", { content_type: contentType, content_id: id, note }, { success: true });

    preview.dataset.note = note;
    if (note.trim()) {
      preview.textContent = `📝 Your note: ${note}`;
      preview.style.display = "block";
    } else {
      preview.style.display = "none";
    }
  });
});
