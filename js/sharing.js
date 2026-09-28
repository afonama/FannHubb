// ==========================================================================
// sharing.js — share a content page via the Web Share API, or copy the link
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  const shareBtn = document.getElementById("share-btn");
  if (!shareBtn) return;

  shareBtn.addEventListener("click", async () => {
    const title = document.getElementById("content-title")?.textContent || "Fan Hub Plus";
    const url = window.location.href;

    if (navigator.share) {
      try {
        await navigator.share({ title, url });
        return;
      } catch (err) {
        // user cancelled the native share sheet — no need to fall through to copy
        if (err.name === "AbortError") return;
      }
    }

    try {
      await navigator.clipboard.writeText(url);
      const original = shareBtn.textContent;
      shareBtn.textContent = "✅ Link copied";
      setTimeout(() => (shareBtn.textContent = original), 1800);
    } catch (err) {
      console.warn("Clipboard copy failed", err);
    }
  });
});
