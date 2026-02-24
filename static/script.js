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
      appendMessage("assistant", data.answer);
      if (data.image_url) appendImage(data.image_url);
      updateOrderPanel(data.order_info);
      chatStatus.textContent = data.intent || "KI-gestützt";
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
  chatMessages.innerHTML = '<div class="message assistant"><div class="message-bubble">Hallo und willkommen bei Cake Dreams! 👋 Wie kann ich Ihnen helfen?</div></div>';
  orderPanel.style.display = "none";
  orderTags.innerHTML = "";
  chatStatus.textContent = "KI-gestützt";
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
