// ==========================================================================
// chatbot.js — optional AI-powered chatbot widget (SRS section 1.6).
// Injects a floating launcher + chat panel on every page that loads this
// script, so it works site-wide without needing a container in each page.
// ==========================================================================

function buildChatbotWidget() {
  const wrapper = document.createElement("div");
  wrapper.id = "fh-chatbot-wrapper";
  wrapper.style.position = "fixed";
  wrapper.style.right = "18px";
  wrapper.style.bottom = "calc(var(--bottom-nav-h) + env(safe-area-inset-bottom, 0px) + 14px)";
  wrapper.style.zIndex = "200";

  wrapper.innerHTML = `
    <button id="fh-chatbot-launcher" style="width:52px; height:52px; border-radius:50%; background:var(--primary); color:var(--primary-contrast); border:none; font-size:1.3rem; box-shadow:var(--shadow-card);">💬</button>
    <div id="fh-chatbot-panel" class="fh-card" style="display:none; position:absolute; right:0; bottom:64px; width:280px; max-height:380px; flex-direction:column;">
      <div style="font-weight:600; margin-bottom:0.5rem;">Fan Hub Assistant</div>
      <div id="fh-chatbot-messages" style="flex:1; overflow-y:auto; font-size:0.85rem; display:flex; flex-direction:column; gap:0.5rem; margin-bottom:0.6rem;">
        <div style="background:var(--surface-raised); border-radius:10px; padding:0.5rem 0.7rem; align-self:flex-start;">
          Hi! Ask me anything about Fan Hub Plus — categories, bookmarks, or how to find something.
        </div>
      </div>
      <form id="fh-chatbot-form" style="display:flex; gap:0.4rem;">
        <input id="fh-chatbot-input" type="text" class="form-control" placeholder="Type a message…" style="font-size:0.85rem;">
        <button type="submit" class="btn-fh-primary" style="padding:0.4rem 0.7rem;">➤</button>
      </form>
    </div>
  `;

  document.body.appendChild(wrapper);

  const launcher = document.getElementById("fh-chatbot-launcher");
  const panel = document.getElementById("fh-chatbot-panel");
  launcher.addEventListener("click", () => {
    panel.style.display = panel.style.display === "none" ? "flex" : "none";
  });

  const form = document.getElementById("fh-chatbot-form");
  const messages = document.getElementById("fh-chatbot-messages");
  const input = document.getElementById("fh-chatbot-input");

  // The API is session-based: omit session_token on the first message, then
  // pass back whatever it returned so the assistant remembers the thread.
  let sessionToken = null;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    const userBubble = document.createElement("div");
    userBubble.style.cssText = "background:var(--primary); color:var(--primary-contrast); border-radius:10px; padding:0.5rem 0.7rem; align-self:flex-end; max-width:85%;";
    userBubble.textContent = text;
    messages.appendChild(userBubble);
    input.value = "";
    messages.scrollTop = messages.scrollHeight;

    const result = await apiSend(
      "/chatbot/message",
      "POST",
      { message: text, session_token: sessionToken },
      { reply: "I'm still connecting to the backend — try again once it's live!" }
    );

    if (result.session_token) sessionToken = result.session_token;

    const botBubble = document.createElement("div");
    botBubble.style.cssText = "background:var(--surface-raised); border-radius:10px; padding:0.5rem 0.7rem; align-self:flex-start; max-width:85%;";
    botBubble.textContent = result.reply || "…";
    messages.appendChild(botBubble);
    messages.scrollTop = messages.scrollHeight;

    if (result.suggestions && result.suggestions.length) {
      const suggestWrap = document.createElement("div");
      suggestWrap.style.cssText = "display:flex; flex-wrap:wrap; gap:0.3rem; align-self:flex-start;";
      result.suggestions.slice(0, 3).forEach((s) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.textContent = s;
        chip.style.cssText = "font-size:0.75rem; border:1px solid var(--border); background:var(--surface); border-radius:999px; padding:0.25rem 0.6rem; color:var(--text);";
        chip.addEventListener("click", () => { input.value = s; form.requestSubmit(); });
        suggestWrap.appendChild(chip);
      });
      messages.appendChild(suggestWrap);
    }
    messages.scrollTop = messages.scrollHeight;
  });
}

document.addEventListener("DOMContentLoaded", buildChatbotWidget);
