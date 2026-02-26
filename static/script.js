// ============================================
// CAKE DREAMS – Chat & UI Script (LangGraph)
// ============================================

// --- DOM Elements ---
const chatFab = document.getElementById("chat-fab");
const chatWidget = document.getElementById("chat-widget");
const chatClose = document.getElementById("chat-close");
const chatMessages = document.getElementById("chat-messages");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const imageCheckbox = document.getElementById("image-checkbox");
const imgBtn = document.getElementById("img-btn");
const resetBtn = document.getElementById("reset-btn");
const chatStatus = document.getElementById("chat-status");
const orderPanel = document.getElementById("order-panel");
const orderTags = document.getElementById("order-tags");
const overlay = document.getElementById("image-overlay");
const overlayImg = document.getElementById("overlay-img");
const navToggle = document.getElementById("nav-toggle");
const navLinks = document.getElementById("nav-links");
const navbar = document.getElementById("navbar");

// --- Streaming Toggle ---
let streamingEnabled = false;

// Create and inject the stream toggle button next to the send button
(function injectStreamToggle() {
  const streamBtn = document.createElement("button");
  streamBtn.id = "stream-btn";
  streamBtn.title = "Streaming-Modus umschalten";
  streamBtn.textContent = "⚡ Stream";
  streamBtn.style.cssText = [
    "padding: 6px 10px",
    "border: 1px solid #ccc",
    "border-radius: 6px",
    "background: #f5f5f5",
    "color: #555",
    "font-size: 12px",
    "cursor: pointer",
    "transition: background 0.2s, color 0.2s",
    "white-space: nowrap",
  ].join(";");

  streamBtn.addEventListener("click", () => {
    streamingEnabled = !streamingEnabled;
    if (streamingEnabled) {
      streamBtn.style.background = "#f5a623";
      streamBtn.style.color = "#fff";
      streamBtn.style.borderColor = "#e09510";
      chatStatus.textContent = "Streaming aktiv";
    } else {
      streamBtn.style.background = "#f5f5f5";
      streamBtn.style.color = "#555";
      streamBtn.style.borderColor = "#ccc";
      chatStatus.textContent = "KI-gestützt";
    }
  });

  // Insert right before the send button's parent container, or after sendBtn
  if (sendBtn && sendBtn.parentNode) {
    sendBtn.parentNode.insertBefore(streamBtn, sendBtn);
  }
})();

// Field labels for order panel
const fieldLabels = {
  anlass: "🎉", gaeste: "👥", geschmack: "🍰",
  form: "📐", schichten: "🧱", fuellung: "🍓",
  dekoration: "🎨", farbe: "🎨"
};

// --- Chat öffnen via Nav oder Hero ---
document.getElementById("open-chat-nav")?.addEventListener("click", (e) => {
  e.preventDefault();
  openChat();
});
document.getElementById("open-chat-hero")?.addEventListener("click", openChat);

// --- Chat Widget Toggle ---
chatFab.addEventListener("click", openChat);
chatClose.addEventListener("click", closeChat);

function openChat() {
  chatWidget.classList.add("open");
  chatFab.classList.add("hidden");
  userInput.focus();
}

function closeChat() {
  chatWidget.classList.remove("open");
  chatFab.classList.remove("hidden");
}

// --- Nachricht senden ---
async function sendMessage() {
  const text = userInput.value.trim();
  if (!text) return;

  appendMessage("user", text);
  userInput.value = "";
  userInput.style.height = "auto";
  sendBtn.disabled = true;
  chatStatus.textContent = "Denkt...";

  if (streamingEnabled) {
    await sendMessageStreaming(text);
    sendBtn.disabled = false;
    userInput.focus();
    return;
  }

  const typing = showTyping("Schreibt...");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text })
    });

    const data = await res.json();
    typing.remove();

    if (res.ok) {
      if (data.session_reset) {
        orderPanel.style.display = "none";
        orderTags.innerHTML = "";
        document.getElementById("new-order-btn")?.parentElement?.remove();
      }
      appendMessage("assistant", data.answer);
      if (data.image_url) appendImage(data.image_url);
      updateOrderPanel(data.order_info);
      chatStatus.textContent = data.intent || "KI-gestützt";
      if (data.order_complete) showNewOrderButton();
    } else {
      appendMessage("assistant", "Fehler: " + (data.detail || "Unbekannt"));
    }
  } catch (err) {
    typing.remove();
    appendMessage("assistant", "Verbindungsfehler. Ist der Server gestartet?");
  }

  sendBtn.disabled = false;
  userInput.focus();
}

// --- Streaming Nachricht via SSE ---
async function sendMessageStreaming(text) {
  chatStatus.textContent = "Streamt...";

  // Create an assistant bubble we'll fill token by token
  const div = document.createElement("div");
  div.className = "message assistant";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = "";
  div.appendChild(bubble);
  chatMessages.appendChild(div);

  try {
    const url = "/api/chat/stream?message=" + encodeURIComponent(text);
    const evtSource = new EventSource(url);

    await new Promise((resolve, reject) => {
      evtSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.token) {
            bubble.textContent += payload.token;
            chatMessages.scrollTop = chatMessages.scrollHeight;
          }
          if (payload.done) {
            evtSource.close();
            chatStatus.textContent = "Streaming abgeschlossen";
            resolve();
          }
          if (payload.error) {
            evtSource.close();
            bubble.textContent = "Fehler: " + payload.error;
            reject(new Error(payload.error));
          }
        } catch (e) {
          // ignore parse errors on individual chunks
        }
      };
      evtSource.onerror = (err) => {
        evtSource.close();
        if (!bubble.textContent) {
          bubble.textContent = "Verbindungsfehler beim Streaming.";
        }
        resolve(); // resolve so the UI unblocks
      };
    });
  } catch (err) {
    if (!bubble.textContent) {
      bubble.textContent = "Streaming-Fehler: " + err.message;
    }
  }
}

// --- Bild generieren (separater Button) ---
async function generateImage() {
  imgBtn.disabled = true;
  const typing = showTyping("🎨 Generiere Kuchenbild...");

  try {
    const res = await fetch("/api/generate-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: "Bild generieren" })
    });
    const data = await res.json();
    typing.remove();

    if (res.ok && data.image_url) {
      appendMessage("assistant", data.answer || "Hier ist Ihr Kuchen!");
      appendImage(data.image_url);
    } else {
      appendMessage("assistant", "Bildgenerierung fehlgeschlagen. Beschreiben Sie Ihren Kuchen genauer.");
    }
  } catch (err) {
    typing.remove();
    appendMessage("assistant", "Verbindungsfehler.");
  }

  imgBtn.disabled = false;
}

// --- Neues Gespräch ---
async function resetChat() {
  try {
    await fetch("/api/reset", { method: "POST" });
  } catch (e) {}
  chatMessages.innerHTML = '<div class="message assistant"><div class="message-bubble">Hallo und willkommen bei Kidstorte! 👋 Wie kann ich Ihnen helfen?</div></div>';
  orderPanel.style.display = "none";
  orderTags.innerHTML = "";
  chatStatus.textContent = "KI-gestützt";
}

// --- "Neue Bestellung"-Button nach abgeschlossener Bestellung ---
function showNewOrderButton() {
  // Nur einmal einfügen
  if (document.getElementById("new-order-btn")) return;
  const div = document.createElement("div");
  div.style.cssText = "display:flex;justify-content:center;margin:12px 0;";
  const btn = document.createElement("button");
  btn.id = "new-order-btn";
  btn.textContent = "🎂 Neue Bestellung starten";
  btn.style.cssText = [
    "padding:10px 20px",
    "background:linear-gradient(135deg,#e8b4a0,#d4956a)",
    "color:#fff",
    "border:none",
    "border-radius:20px",
    "font-size:14px",
    "font-weight:600",
    "cursor:pointer",
    "box-shadow:0 2px 8px rgba(0,0,0,0.15)",
  ].join(";");
  btn.addEventListener("click", () => {
    div.remove();
    resetChat();
  });
  div.appendChild(btn);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// --- Hilfsfunktionen ---
function appendMessage(role, text) {
  const div = document.createElement("div");
  div.className = "message " + (role === "user" ? "user" : "assistant");
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = text;
  div.appendChild(bubble);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendImage(url) {
  const div = document.createElement("div");
  div.className = "message assistant";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble message-image";
  const img = document.createElement("img");
  img.src = url;
  img.alt = "Kuchen Vorschau";
  img.onclick = () => {
    overlayImg.src = url;
    overlay.classList.add("active");
  };
  bubble.appendChild(img);
  div.appendChild(bubble);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showTyping(text) {
  const div = document.createElement("div");
  div.className = "message assistant";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble typing-indicator";
  bubble.textContent = text;
  div.appendChild(bubble);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function updateOrderPanel(info) {
  if (!info || Object.keys(info).length === 0) {
    orderPanel.style.display = "none";
    return;
  }
  orderPanel.style.display = "block";
  orderTags.innerHTML = "";
  for (const [key, val] of Object.entries(info)) {
    const tag = document.createElement("span");
    tag.className = "order-tag";
    tag.textContent = (fieldLabels[key] || "📌") + " " + val;
    orderTags.appendChild(tag);
  }
}

// --- Event Listeners ---
sendBtn.addEventListener("click", sendMessage);
imgBtn.addEventListener("click", generateImage);
resetBtn.addEventListener("click", resetChat);

userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Auto-resize textarea
userInput.addEventListener("input", () => {
  userInput.style.height = "auto";
  userInput.style.height = Math.min(userInput.scrollHeight, 100) + "px";
});

// Overlay schließen
overlay.addEventListener("click", () => overlay.classList.remove("active"));

// --- Mobile Nav Toggle ---
navToggle?.addEventListener("click", () => {
  navLinks.classList.toggle("open");
});

// Navbar Scroll-Effekt
window.addEventListener("scroll", () => {
  if (window.scrollY > 50) {
    navbar.classList.add("scrolled");
  } else {
    navbar.classList.remove("scrolled");
  }
});

// Nav-Links schließen bei Klick
document.querySelectorAll(".nav-links a").forEach(link => {
  link.addEventListener("click", () => navLinks.classList.remove("open"));
});
