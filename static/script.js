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
const overlay = document.getElementById("image-overlay");
const overlayImg = document.getElementById("overlay-img");
const navToggle = document.getElementById("nav-toggle");
const navLinks = document.getElementById("nav-links");
const navbar = document.getElementById("navbar");


// Fortschrittsanzeige DOM-Referenzen
const progressContainer = document.getElementById("progress-bar-container");
const progressFill = document.getElementById("progress-fill");
const progressCount = document.getElementById("progress-count");
const progressSteps = document.getElementById("progress-steps");

// Field labels für Progressbar-Buttons
const fieldLabels = {
  anlass: "Anlass",
  gaeste: "Gäste",
  geschmack: "Geschmack",
  form: "Form",
  schichten: "Schichten",
  fuellung: "Füllung",
  dekoration: "Dekoration",
  farbe: "Farbe",
  allergien: "Allergien",
  beschriftung: "Beschriftung",
  abholung: "Abholung",
  lieferadresse: "Lieferadresse",
  liefertermin: "Liefertermin"
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

// --- Streaming-Modus: Wort-für-Wort wie ChatGPT ---
let useStreaming = true; // Streaming standardmäßig AN

async function sendMessage() {
  const text = userInput.value.trim();
  if (!text) return;

  appendMessage("user", text);
  userInput.value = "";
  userInput.style.height = "auto";
  sendBtn.disabled = true;

  if (useStreaming) {
    await sendMessageStreaming(text);
  } else {
    await sendMessageClassic(text);
  }

  sendBtn.disabled = false;
  userInput.focus();
}

// ── Streaming: SSE Wort-für-Wort ──
async function sendMessageStreaming(text) {
  chatStatus.textContent = "Denkt...";
  let pendingImagePlaceholder = null;

  // Leere Bot-Bubble erstellen die wir live befüllen
  const div = document.createElement("div");
  div.className = "message assistant";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = "";
  div.appendChild(bubble);
  chatMessages.appendChild(div);

  // Cursor-Animation hinzufügen
  bubble.classList.add("streaming-cursor");

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text })
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // Unvollständige Zeile behalten

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6);
        if (!jsonStr.trim()) continue;

        try {
          const event = JSON.parse(jsonStr);

          if (event.status === "thinking") {
            chatStatus.textContent = "Denkt...";
          } else if (event.status === "streaming") {
            chatStatus.textContent = "Schreibt...";
          } else if (event.token) {
            // Wort-für-Wort anzeigen (als Text während Streaming)
            bubble.textContent += event.token;
            chatMessages.scrollTop = chatMessages.scrollHeight;
          } else if (event.done) {
            // Streaming fertig — Cursor entfernen
            bubble.classList.remove("streaming-cursor");

            // HTML-Tabellen rendern (z.B. Preisberechnung)
            const fullText = bubble.textContent;
            if (fullText.includes("<table") || fullText.includes("<b>") || fullText.includes("<br")) {
              bubble.innerHTML = sanitizeHtml(fullText);
            }

            // Metadaten verarbeiten (Bilder, Progress, etc.)
            if (event.image_url || event.image_url_cut) {
              appendImages(event.image_url, event.image_url_cut, event.reference_image_url);
            } else if (event.image_pending) {
              // Bild wird parallel generiert → Platzhalter zeigen, später ersetzen
              pendingImagePlaceholder = appendImagePlaceholder();
              chatStatus.textContent = "Generiere Bild...";
            }
            updateProgressBar(event.question_todo);
            chatStatus.textContent = event.intent || "KI-gestützt";

            // Kalender-Widget: NUR wenn Termin noch NICHT festgelegt
            const todo = event.question_todo || {};
            const terminDone = todo["liefertermin"] === "answered";
            // Wenn Termin geändert wird (change-Intent), Kalender zurücksetzen
            if (todo["liefertermin"] === "asked") calendarWidgetShown = false;
            const showCal = !terminDone && (
              todo["liefertermin"] === "asked" ||
              (todo["abholung"] === "answered" && todo["liefertermin"] !== "answered") ||
              (bubble.textContent && /termin|wann.*liefer|datum|abhol.*tag|liefer.*tag/i.test(bubble.textContent))
            );
            if (showCal) showCalendarWidget();

            // Quick-Option-Buttons für das aktuell gefragte Feld
            if (event.current_field && fieldQuickOptions[event.current_field]) {
              showQuickOptions(event.current_field);
            }

            if (event.show_address_form) {
              showAddressForm(!event.is_pickup);
            }
            else if (event.order_finalized) showNewOrderButton();
          } else if (event.image_ready) {
            // Bild fertig → Platzhalter durch echtes Bild ersetzen
            if (pendingImagePlaceholder && pendingImagePlaceholder.parentNode) {
              pendingImagePlaceholder.parentNode.removeChild(pendingImagePlaceholder);
              pendingImagePlaceholder = null;
            }
            if (event.image_url || event.image_url_cut) {
              appendImages(event.image_url, event.image_url_cut, event.reference_image_url);
            } else {
              appendMessage("assistant", "Das Vorschaubild konnte leider nicht generiert werden. Möchten Sie es nochmal versuchen?");
            }
            chatStatus.textContent = "KI-gestützt";
          } else if (event.error) {
            bubble.classList.remove("streaming-cursor");
            bubble.textContent = "Fehler: " + event.error;
          }
        } catch (e) { /* Skip unparseable lines */ }
      }
    }

    // Falls Cursor noch da ist (z.B. bei Abbruch)
    bubble.classList.remove("streaming-cursor");

  } catch (err) {
    bubble.classList.remove("streaming-cursor");
    bubble.textContent = "Verbindungsfehler. Ist der Server gestartet?";
  }
}

// ── Klassischer Modus: Ganze Antwort auf einmal (Fallback) ──
async function sendMessageClassic(text) {
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
      if (data.image_url || data.image_url_cut) appendImages(data.image_url, data.image_url_cut, data.reference_image_url);
      updateProgressBar(data.question_todo);
      chatStatus.textContent = data.intent || "KI-gestützt";
      const todo = data.question_todo || {};
      const terminDone = todo["liefertermin"] === "answered";
      const showCal = !terminDone && (
        todo["liefertermin"] === "asked" ||
        (todo["abholung"] === "answered" && todo["liefertermin"] !== "answered") ||
        (data.answer && /termin|wann.*liefer|datum|abhol.*tag|liefer.*tag/i.test(data.answer))
      );
      if (showCal) showCalendarWidget();
      // Quick-Option-Buttons
      if (data.current_field && fieldQuickOptions[data.current_field]) {
        showQuickOptions(data.current_field);
      }
      if (data.show_address_form) {
        showAddressForm(!data.is_pickup);
      }
      else if (data.order_finalized) showNewOrderButton();
    } else {
      appendMessage("assistant", "Fehler: " + (data.detail || "Unbekannt"));
    }
  } catch (err) {
    typing.remove();
    appendMessage("assistant", "Verbindungsfehler. Ist der Server gestartet?");
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

    if (res.ok && (data.image_url || data.image_url_cut)) {
      appendMessage("assistant", data.answer || "Hier ist Ihr Kuchen!");
      appendImages(data.image_url, data.image_url_cut, data.reference_image_url);
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
  progressContainer.style.display = "none";
  progressFill.style.width = "0%";
  progressCount.textContent = "0 / 7";
  progressSteps.innerHTML = "";
  chatStatus.textContent = "KI-gestützt";
  // Adressformular verstecken + zurücksetzen
  const addrForm = document.getElementById("address-form-container");
  if (addrForm) addrForm.style.display = "none";
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
  if (role === "assistant" && text.includes("<table")) {
    // HTML-Tabelle im Bot-Text (z.B. Preisberechnung) → sicher rendern
    bubble.innerHTML = sanitizeHtml(text);
  } else {
    bubble.textContent = text;
  }
  div.appendChild(bubble);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function sanitizeHtml(html) {
  const allowed = ["TABLE", "TR", "TD", "TH", "THEAD", "TBODY", "B", "STRONG", "BR", "EM", "P"];
  const temp = document.createElement("div");
  temp.innerHTML = html;
  // Gefährliche Elemente entfernen
  temp.querySelectorAll("script, style, iframe, object, embed, link").forEach(el => el.remove());
  // Event-Handler entfernen
  temp.querySelectorAll("*").forEach(el => {
    for (const attr of [...el.attributes]) {
      if (attr.name.startsWith("on") || (attr.name === "href" && attr.value.startsWith("javascript:"))) {
        el.removeAttribute(attr.name);
      }
    }
  });
  return temp.innerHTML;
}

// Platzhalter-Bubble während das Bild generiert wird.
// Gibt die DOM-Node zurück, damit sie später durch das echte Bild ersetzt werden kann.
function appendImagePlaceholder() {
  const div = document.createElement("div");
  div.className = "message assistant image-placeholder";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble message-image";
  const inner = document.createElement("div");
  inner.className = "img-preview-row image-loading";
  inner.innerHTML =
    '<div class="img-preview-wrapper">' +
      '<div class="img-preview-label">Vorschaubild wird gemalt…</div>' +
      '<div class="image-loading-box">' +
        '<div class="image-loading-spinner"></div>' +
        '<div class="image-loading-text">🎨 Einen Moment...</div>' +
      '</div>' +
    '</div>';
  bubble.appendChild(inner);
  div.appendChild(bubble);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function appendImages(urlExterior, urlCut, urlReference) {
  const div = document.createElement("div");
  div.className = "message assistant";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble message-image";

  const makeImg = (url, label, cssClass) => {
    const wrapper = document.createElement("div");
    wrapper.className = "img-preview-wrapper" + (cssClass ? " " + cssClass : "");
    const caption = document.createElement("div");
    caption.className = "img-preview-label";
    caption.textContent = label;
    const img = document.createElement("img");
    img.src = url;
    img.alt = label;
    img.onclick = () => {
      overlayImg.src = url;
      overlay.classList.add("active");
    };
    wrapper.appendChild(caption);
    wrapper.appendChild(img);
    return wrapper;
  };

  const row = document.createElement("div");
  row.className = "img-preview-row";
  if (urlExterior) row.appendChild(makeImg(urlExterior, "Ihr Wunschkuchen"));
  if (urlCut) row.appendChild(makeImg(urlCut, "Anschnitt"));

  bubble.appendChild(row);

  // Referenzbild aus Portfolio (kleiner, unter dem Hauptbild)
  if (urlReference) {
    const refRow = document.createElement("div");
    refRow.className = "reference-image-container";
    refRow.appendChild(makeImg(urlReference, "Aus unserem Portfolio", "reference-img"));
    bubble.appendChild(refRow);
  }

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


// --- Fortschrittsanzeige aktualisieren ---
function updateProgressBar(todo) {
  if (!todo || Object.keys(todo).length === 0) return;

  // Nur anzeigen sobald mindestens eine Frage gefragt oder beantwortet wurde
  const hasStarted = Object.values(todo).some(s => s !== "pending");
  if (!hasStarted) return;

  progressContainer.style.display = "block";

  const entries = Object.entries(todo);
  const total = entries.length;
  const answered = entries.filter(([, s]) => s === "answered").length;
  const pct = total > 0 ? Math.round((answered / total) * 100) : 0;

  // Balken + Zähler aktualisieren
  progressFill.style.width = pct + "%";
  progressCount.textContent = `${answered} / ${total}`;

  // Farbe bei 100%: Grün-Akzent
  if (answered === total) {
    progressFill.style.background = "linear-gradient(90deg, #4CAF50, #2e7d32)";
  } else {
    progressFill.style.background = "";  // CSS-Standard zurück
  }

  // Einzelne Schritte rendern
  progressSteps.innerHTML = "";
  const icons = { answered: "✅", asked: "⏳", pending: "○" };
  for (const [field, status] of entries) {
    const chip = document.createElement("span");
    chip.className = `progress-step ${status}`;
    chip.innerHTML = `<span class="progress-step-icon">${icons[status] || "○"}</span>${fieldLabels[field] || field}`;
    chip.title = status === "answered"
      ? `${fieldLabels[field] || field}: beantwortet`
      : status === "asked"
      ? `${fieldLabels[field] || field}: gefragt, noch offen`
      : `${fieldLabels[field] || field}: noch nicht gefragt`;
    progressSteps.appendChild(chip);
  }
}

// --- Adressformular anzeigen ---
// isDelivery wird vom Event übergeben (true = Lieferung, false = Abholung)
let formIsDelivery = true;

function showAddressForm(isDelivery) {
  formIsDelivery = (isDelivery !== false); // Default: Lieferung
  const container = document.getElementById("address-form-container");
  const deliveryFields = document.getElementById("addr-delivery-fields");
  const title = document.getElementById("addr-form-title");

  if (!container) return;

  if (formIsDelivery) {
    // Lieferung: volles Formular
    title.textContent = "Kontakt- und Lieferadresse";
    deliveryFields.style.display = "block";
  } else {
    // Abholung: nur Name, Telefon, E-Mail
    title.textContent = "Ihre Kontaktdaten (Abholung)";
    deliveryFields.style.display = "none";
    // Adress-Felder leeren damit keine alten Werte gesendet werden
    document.getElementById("addr-street").value = "";
    document.getElementById("addr-plz").value = "";
    document.getElementById("addr-city").value = "";
  }

  container.style.display = "block";
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// --- Formular-Validierung ---
function validateAddressForm() {
  const fields = {
    name:   document.getElementById("addr-name").value.trim(),
    street: document.getElementById("addr-street").value.trim(),
    plz:    document.getElementById("addr-plz").value.trim(),
    city:   document.getElementById("addr-city").value.trim(),
    phone:  document.getElementById("addr-phone").value.trim(),
    email:  document.getElementById("addr-email").value.trim(),
  };

  const errors = [];

  // Pflichtfelder (immer)
  if (!fields.name || fields.name.length < 2)
    errors.push("Bitte geben Sie Ihren vollständigen Namen ein (min. 2 Zeichen).");
  if (!fields.phone || !/^[\d\s\+\-\/()]{6,20}$/.test(fields.phone))
    errors.push("Bitte geben Sie eine gültige Telefonnummer ein (nur Ziffern, +, -, Leerzeichen).");
  if (!fields.email || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(fields.email))
    errors.push("Bitte geben Sie eine gültige E-Mail-Adresse ein (z.B. name@beispiel.de).");

  // Adress-Felder nur bei Lieferung validieren
  if (formIsDelivery) {
    if (!fields.street || fields.street.length < 5)
      errors.push("Bitte geben Sie eine gültige Straße mit Hausnummer ein.");
    if (!fields.plz || !/^\d{5}$/.test(fields.plz))
      errors.push("Die PLZ muss genau 5 Ziffern haben (z.B. 50667).");
    if (!fields.city || fields.city.length < 2)
      errors.push("Bitte geben Sie einen gültigen Stadtnamen ein.");
  }

  return { fields, errors };
}

// --- Inline-Fehleranzeige ---
function showFieldErrors(errors) {
  // Alte Fehler entfernen
  document.querySelectorAll(".addr-error").forEach(el => el.remove());
  document.querySelectorAll(".addr-input-error").forEach(el => el.classList.remove("addr-input-error"));

  if (errors.length === 0) return;

  // Fehler unter dem Formular anzeigen
  const container = document.querySelector(".address-form-fields");
  const errorDiv = document.createElement("div");
  errorDiv.className = "addr-error";
  errorDiv.innerHTML = errors.map(e => `<div>${e}</div>`).join("");
  container.appendChild(errorDiv);

  // Fehlerhafte Felder rot markieren
  const fieldMap = {
    "Name": "addr-name", "Straße": "addr-street", "PLZ": "addr-plz",
    "Stadt": "addr-city", "Telefon": "addr-phone", "E-Mail": "addr-email"
  };
  for (const [label, id] of Object.entries(fieldMap)) {
    if (errors.some(e => e.toLowerCase().includes(label.toLowerCase()))) {
      document.getElementById(id)?.classList.add("addr-input-error");
    }
  }
}

// --- Bestätigungs-Vorschau ---
function showOrderConfirmation(fields, onConfirm) {
  // Altes Overlay entfernen falls vorhanden
  document.getElementById("order-confirm-overlay")?.remove();

  const overlay = document.createElement("div");
  overlay.id = "order-confirm-overlay";
  overlay.className = "confirm-overlay";
  const addrRow = formIsDelivery
    ? `<tr><td><strong>Adresse:</strong></td><td>${fields.street}, ${fields.plz} ${fields.city}</td></tr>`
    : `<tr><td><strong>Abholung:</strong></td><td>Im Laden</td></tr>`;
  overlay.innerHTML = `
    <div class="confirm-box">
      <h3>Bestellung prüfen</h3>
      <p>Bitte überprüfen Sie Ihre Daten:</p>
      <table class="confirm-table">
        <tr><td><strong>Name:</strong></td><td>${fields.name}</td></tr>
        ${addrRow}
        <tr><td><strong>Telefon:</strong></td><td>${fields.phone}</td></tr>
        <tr><td><strong>E-Mail:</strong></td><td>${fields.email}</td></tr>
      </table>
      <div class="confirm-buttons">
        <button class="btn-confirm-yes">Jetzt bestellen</button>
        <button class="btn-confirm-no">Zurück / Korrigieren</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.querySelector(".btn-confirm-yes").addEventListener("click", () => {
    overlay.remove();
    onConfirm();
  });
  overlay.querySelector(".btn-confirm-no").addEventListener("click", () => {
    overlay.remove();
  });
}

// --- Adressformular absenden ---
async function submitAddress() {
  const { fields, errors } = validateAddressForm();

  // Validierung
  showFieldErrors(errors);
  if (errors.length > 0) return;

  // Bestätigungs-Vorschau anzeigen
  showOrderConfirmation(fields, () => doSubmitOrder(fields));
}

async function doSubmitOrder(fields) {
  const submitBtn = document.getElementById("submit-address-btn");
  submitBtn.disabled = true;
  submitBtn.textContent = "Wird gesendet...";

  try {
    const res = await fetch("/api/submit-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields)
    });

    const data = await res.json();

    // Formular verstecken
    document.getElementById("address-form-container").style.display = "none";

    if (res.ok) {
      appendMessage("assistant", data.message || "Ihre Bestellung wurde erfolgreich aufgenommen! Sie erhalten in Kürze eine Bestätigung per E-Mail.");
      if (data.pdf_url) appendPdfLink(data.pdf_url, data.order_id);
      showNewOrderButton();
    } else {
      appendMessage("assistant", "Fehler: " + (data.detail || "Bestellung konnte nicht gespeichert werden."));
    }
  } catch (err) {
    appendMessage("assistant", "Verbindungsfehler beim Absenden der Bestellung.");
  }

  submitBtn.disabled = false;
  submitBtn.textContent = "Bestellung abschicken";
}

// --- Event Listeners ---
sendBtn.addEventListener("click", sendMessage);
imgBtn.addEventListener("click", generateImage);
resetBtn.addEventListener("click", resetChat);
document.getElementById("submit-address-btn")?.addEventListener("click", submitAddress);

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

// ── PDF-Download-Link im Chat ────────────────────────────────────
function appendPdfLink(pdfUrl, orderId) {
  const div = document.createElement("div");
  div.className = "message assistant";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  const link = document.createElement("a");
  link.href = pdfUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.innerHTML = "📄 Bestellbestätigung als PDF herunterladen";
  link.style.cssText = [
    "display:inline-flex", "align-items:center", "gap:6px",
    "background:linear-gradient(135deg,#e8b4a0,#d4956a)",
    "color:#fff", "padding:8px 14px", "border-radius:8px",
    "text-decoration:none", "font-weight:600", "font-size:0.88rem",
    "transition:opacity 0.2s"
  ].join(";");
  link.onmouseover = () => link.style.opacity = "0.85";
  link.onmouseout = () => link.style.opacity = "1";
  bubble.appendChild(link);
  div.appendChild(bubble);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── Quick-Option-Buttons für Bestellfelder ──────────────────────
const fieldQuickOptions = {
  geschmack: {
    label: "Unsere Kuchen",
    options: [
      { text: "Schokolade", sub: "Chocolate Dream", prices: "ab 35 €" },
      { text: "Vanille", sub: "Vanilla Heaven", prices: "ab 30 €" },
      { text: "Erdbeere", sub: "Strawberry Bliss", prices: "ab 35 €" },
      { text: "Beeren (vegan)", sub: "Berry Delight 🌱", prices: "ab 35 €" },
      { text: "Karamell", sub: "Caramel Crunch", prices: "ab 38 €" },
      { text: "Zitrone (glutenfrei)", sub: "Lemon Zest", prices: "ab 38 €" },
    ]
  },
  form: {
    label: "Kuchenform",
    options: [
      { text: "Rund", sub: "Standard", prices: "" },
      { text: "Eckig", sub: "Standard", prices: "" },
      { text: "Herzform", sub: "+10 €", prices: "" },
    ]
  },
  schichten: {
    label: "Schichten / Etagen",
    options: [
      { text: "1 Schicht", sub: "Standard", prices: "" },
      { text: "2 Schichten", sub: "+15 €", prices: "" },
      { text: "3 Schichten", sub: "+30 €", prices: "" },
    ]
  },
  // dekoration: KEINE Buttons — Kunde soll frei beschreiben (z.B. "Elsa mit Schneeflocken")
  // damit das Vorschaubild den Kundenwunsch genau abbilden kann
  abholung: {
    label: "Abholung oder Lieferung",
    options: [
      { text: "Abholung", sub: "kostenlos", prices: "" },
      { text: "Lieferung", sub: "ab 10 €", prices: "" },
    ]
  },
  fuellung: {
    label: "Füllung wählen",
    options: [
      { text: "Schokolade", sub: "", prices: "" },
      { text: "Vanille", sub: "", prices: "" },
      { text: "Erdbeere", sub: "", prices: "" },
      { text: "Himbeere", sub: "", prices: "" },
      { text: "Karamell", sub: "", prices: "" },
      { text: "Zitrone", sub: "", prices: "" },
    ]
  },
};

function showQuickOptions(field) {
  const config = fieldQuickOptions[field];
  if (!config) return;

  // Alte Quick-Options entfernen
  document.querySelectorAll(".quick-options-container").forEach(el => el.remove());

  const container = document.createElement("div");
  container.className = "message assistant";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble quick-options-container";

  const label = document.createElement("div");
  label.className = "quick-options-label";
  label.textContent = config.label;
  bubble.appendChild(label);

  const grid = document.createElement("div");
  grid.className = "quick-options-grid";

  for (const opt of config.options) {
    const btn = document.createElement("button");
    btn.className = "quick-option-btn";

    const mainText = document.createElement("span");
    mainText.className = "quick-option-main";
    mainText.textContent = opt.text;
    btn.appendChild(mainText);

    if (opt.sub) {
      const subText = document.createElement("span");
      subText.className = "quick-option-sub";
      subText.textContent = opt.sub;
      btn.appendChild(subText);
    }

    if (opt.prices) {
      const priceText = document.createElement("span");
      priceText.className = "quick-option-price";
      priceText.textContent = opt.prices;
      btn.appendChild(priceText);
    }

    btn.addEventListener("click", () => {
      container.remove();
      userInput.value = opt.text;
      sendMessage();
    });

    grid.appendChild(btn);
  }

  bubble.appendChild(grid);
  container.appendChild(bubble);
  chatMessages.appendChild(container);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── Kalender-Widget im Chat ──────────────────────────────────────
let calendarWidgetShown = false;

async function showCalendarWidget() {
  if (calendarWidgetShown) return;
  calendarWidgetShown = true;

  // Lade verfügbare Termine + Kalender-Status
  let availableDates = [];
  let maxPerDay = 5;
  let calendarMode = "local";
  try {
    const [datesRes, statusRes] = await Promise.all([
      fetch("/api/available-dates?days=60"),
      fetch("/api/calendar/status"),
    ]);
    const datesData = await datesRes.json();
    const statusData = await statusRes.json();
    availableDates = datesData.available || [];
    maxPerDay = datesData.max_per_day || 5;
    calendarMode = statusData.mode || "local";
  } catch (e) {}

  const availableSet = new Set(availableDates);
  const today = new Date();
  const year = today.getFullYear();
  const mon = today.getMonth();

  const div = document.createElement("div");
  div.className = "message assistant";
  div.id = "calendar-widget-msg";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble cal-bubble";

  function renderMonth(y, m) {
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const firstDay = (new Date(y, m, 1).getDay() + 6) % 7;
    const monthNames = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"];
    const dayNames = ["Mo","Di","Mi","Do","Fr","Sa","So"];

    let html = `<div class="cal-header">
      <button class="cal-nav" id="cal-prev">‹</button>
      <span class="cal-month-label">${monthNames[m]} ${y}</span>
      <button class="cal-nav" id="cal-next">›</button>
    </div>
    <div class="cal-grid">`;
    dayNames.forEach(d => html += `<div class="cal-day-name">${d}</div>`);
    for (let i = 0; i < firstDay; i++) html += `<div></div>`;
    for (let d = 1; d <= daysInMonth; d++) {
      const pad = n => String(n).padStart(2,"0");
      const key = `${y}-${pad(m+1)}-${pad(d)}`;
      const dateObj = new Date(y, m, d);
      const isPast = dateObj <= today;
      const isSunday = dateObj.getDay() === 0;
      const isTooSoon = dateObj <= new Date(today.getTime() + 2 * 86400000);
      const isAvail = availableSet.has(key);

      let cls = "cal-day-cell";
      let title = "";
      if (isPast || isTooSoon) {
        cls += " cal-cell-past";
        title = isPast ? "Vergangen" : "Min. 2 Tage Vorlauf";
      } else if (isSunday) {
        cls += " cal-cell-full";
        title = "Sonntag — geschlossen";
      } else if (isAvail) {
        cls += " cal-cell-avail";
        title = "Verfügbar — klicken zum Auswählen";
      } else {
        cls += " cal-cell-full";
        title = "Ausgebucht";
      }
      html += `<div class="${cls}" data-date="${key}" title="${title}">${d}</div>`;
    }
    html += "</div>";

    // Legende
    html += `<div class="cal-legend">
      <span class="cal-legend-item"><span class="cal-legend-dot cal-dot-avail"></span> Verfügbar</span>
      <span class="cal-legend-item"><span class="cal-legend-dot cal-dot-full"></span> Ausgebucht</span>
      <span class="cal-legend-item"><span class="cal-legend-dot cal-dot-past"></span> Nicht wählbar</span>
    </div>`;

    const modeLabel = calendarMode === "calcom" ? "cal.com" : "Lokal";
    bubble.innerHTML = `<p style="font-size:0.85rem;color:#555;margin-bottom:8px;">📅 <b>Wunschtermin wählen</b> <span style="font-size:0.72rem;color:#aaa;margin-left:4px;">(${modeLabel})</span></p>` + html;

    // Klick-Events für verfügbare Tage
    bubble.querySelectorAll(".cal-cell-avail").forEach(cell => {
      cell.addEventListener("click", () => {
        const date = cell.dataset.date;
        const [yr, mo, dy] = date.split("-");
        const formatted = `${dy}.${mo}.${yr}`;

        // Ausgewählten Tag hervorheben
        bubble.querySelectorAll(".cal-cell-selected").forEach(el => el.classList.remove("cal-cell-selected"));
        cell.classList.add("cal-cell-selected");

        // Kurz warten, dann als Nachricht senden
        setTimeout(() => {
          div.remove();
          calendarWidgetShown = false;
          userInput.value = `Lieferung am ${formatted}`;
          sendMessage();
        }, 300);
      });
    });

    bubble.querySelector("#cal-prev")?.addEventListener("click", () => {
      let nm = m - 1, ny = y;
      if (nm < 0) { nm = 11; ny--; }
      renderMonth(ny, nm);
    });
    bubble.querySelector("#cal-next")?.addEventListener("click", () => {
      let nm = m + 1, ny = y;
      if (nm > 11) { nm = 0; ny++; }
      renderMonth(ny, nm);
    });
  }

  renderMonth(year, mon);
  div.appendChild(bubble);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}
