const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");

// ============================================================
// ICON HELPERS
// ============================================================
function renderIconSvg(IconComponent, color = "#000000", size = 256) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
}

async function iconToBase64Png(IconComponent, color, size = 256) {
  const svg = renderIconSvg(IconComponent, color, size);
  const pngBuffer = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + pngBuffer.toString("base64");
}

// ============================================================
// COLOR PALETTE — Warm Bakery Tech Theme
// ============================================================
const C = {
  dark:      "2B1B17",   // Deep chocolate brown
  primary:   "C2704E",   // Warm terracotta/cake
  secondary: "8B5E3C",   // Medium brown
  accent:    "E8A87C",   // Peach/warm accent
  light:     "FDF6F0",   // Cream white
  cream:     "F5EDE3",   // Warm cream
  sage:      "7BA seventeen", // Sage
  text:      "2B1B17",   // Dark text
  textLight: "FFFFFF",   // White text
  muted:     "8C7B6F",   // Muted brown
  card:      "FFFFFF",   // White cards
  green:     "5B8C5A",   // Success green
  blue:      "4A7C9B",   // Tech blue
  purple:    "7B6B8D",   // Purple accent
  orange:    "D4856B",   // Orange
  red:       "C2574A",   // Alert red
};

// Fix sage
C.sage = "7BA68A";

// ============================================================
// HELPER FACTORIES (avoid object reuse corruption)
// ============================================================
const makeShadow = () => ({ type: "outer", blur: 4, offset: 2, angle: 135, color: "000000", opacity: 0.12 });
const makeCardShadow = () => ({ type: "outer", blur: 6, offset: 3, angle: 135, color: "000000", opacity: 0.15 });

function addFooter(slide, slideNum, totalSlides) {
  // Bottom bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 5.25, w: 10, h: 0.375,
    fill: { color: C.dark }
  });
  slide.addText("Kidstorte — KI-gestützter Bestellassistent", {
    x: 0.5, y: 5.25, w: 7, h: 0.375,
    fontSize: 8, color: C.accent, fontFace: "Calibri", valign: "middle", margin: 0
  });
  slide.addText(`${slideNum} / ${totalSlides}`, {
    x: 8.5, y: 5.25, w: 1, h: 0.375,
    fontSize: 8, color: C.accent, fontFace: "Calibri", align: "right", valign: "middle", margin: 0
  });
}

function addSectionHeader(slide, number, title) {
  // Accent circle with number
  slide.addShape(pres.shapes.OVAL, {
    x: 0.5, y: 0.35, w: 0.5, h: 0.5,
    fill: { color: C.primary }
  });
  slide.addText(String(number), {
    x: 0.5, y: 0.35, w: 0.5, h: 0.5,
    fontSize: 16, color: C.textLight, fontFace: "Georgia", bold: true,
    align: "center", valign: "middle", margin: 0
  });
  // Title
  slide.addText(title, {
    x: 1.15, y: 0.3, w: 8.35, h: 0.6,
    fontSize: 28, color: C.dark, fontFace: "Georgia", bold: true, margin: 0
  });
  // Thin accent line
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 0.95, w: 9, h: 0.03,
    fill: { color: C.accent }
  });
}

function addCard(slide, x, y, w, h, fillColor) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: fillColor || C.card },
    shadow: makeCardShadow(),
    line: { color: C.cream, width: 0.5 }
  });
}

function addIconCircle(slide, x, y, size, bgColor, label) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w: size, h: size,
    fill: { color: bgColor }
  });
  slide.addText(label, {
    x, y, w: size, h: size,
    fontSize: 14, color: C.textLight, fontFace: "Calibri", bold: true,
    align: "center", valign: "middle", margin: 0
  });
}

// ============================================================
// CREATE PRESENTATION
// ============================================================
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Schamja Shahag";
pres.title = "Kidstorte — KI-gestützter Bestellassistent";

const TOTAL = 25;

// ============================================================
// SLIDE 1: TITLE
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.dark };

  // Decorative top accent
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.06,
    fill: { color: C.primary }
  });

  // Main title
  slide.addText("KIDSTORTE", {
    x: 0.8, y: 1.0, w: 8.4, h: 1.2,
    fontSize: 54, color: C.textLight, fontFace: "Georgia", bold: true,
    charSpacing: 8, margin: 0
  });

  // Subtitle
  slide.addText("KI-gestützter Bestellassistent für Tortenbestellungen", {
    x: 0.8, y: 2.1, w: 8.4, h: 0.6,
    fontSize: 20, color: C.accent, fontFace: "Calibri", margin: 0
  });

  // Accent line
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.8, y: 2.85, w: 2.5, h: 0.04,
    fill: { color: C.primary }
  });

  // Tech stack pills
  const techs = ["LangGraph", "GPT-4o", "ChromaDB", "FastAPI", "LangSmith", "DALL-E"];
  techs.forEach((t, i) => {
    const tx = 0.8 + i * 1.45;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: tx, y: 3.15, w: 1.3, h: 0.35,
      fill: { color: C.secondary },
      line: { color: C.accent, width: 0.5 }
    });
    slide.addText(t, {
      x: tx, y: 3.15, w: 1.3, h: 0.35,
      fontSize: 10, color: C.textLight, fontFace: "Calibri", bold: true,
      align: "center", valign: "middle", margin: 0
    });
  });

  // Author + date
  slide.addText("Schamja Shahag  ·  Masterschool Demo Day  ·  März 2026", {
    x: 0.8, y: 4.3, w: 8.4, h: 0.4,
    fontSize: 13, color: C.muted, fontFace: "Calibri", margin: 0
  });

  // Decorative emoji
  slide.addText("🎂", {
    x: 8.5, y: 1.0, w: 1, h: 1,
    fontSize: 48, align: "center", valign: "middle", margin: 0
  });
})();

// ============================================================
// SLIDE 2: AGENDA
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "📋", "Agenda — 40 Minuten");
  addFooter(slide, 2, TOTAL);

  const items = [
    { num: "01", title: "Problem & Lösung", time: "3 Min", color: C.primary },
    { num: "02", title: "Tech Stack & Architektur", time: "5 Min", color: C.secondary },
    { num: "03", title: "State Machine & Nodes", time: "6 Min", color: C.blue },
    { num: "04", title: "RAG, LLM & Bildgenerierung", time: "5 Min", color: C.green },
    { num: "05", title: "Session, DB & Services", time: "4 Min", color: C.purple },
    { num: "06", title: "Frontend & UX", time: "3 Min", color: C.orange },
    { num: "07", title: "Monitoring & Tracing", time: "3 Min", color: C.sage },
    { num: "08", title: "Live Demo", time: "8 Min", color: C.red },
    { num: "09", title: "Herausforderungen & Learnings", time: "3 Min", color: C.primary },
  ];

  items.forEach((item, i) => {
    const yy = 1.2 + i * 0.45;
    // Number circle
    slide.addShape(pres.shapes.OVAL, {
      x: 0.7, y: yy + 0.02, w: 0.35, h: 0.35,
      fill: { color: item.color }
    });
    slide.addText(item.num, {
      x: 0.7, y: yy + 0.02, w: 0.35, h: 0.35,
      fontSize: 10, color: C.textLight, fontFace: "Calibri", bold: true,
      align: "center", valign: "middle", margin: 0
    });
    // Title
    slide.addText(item.title, {
      x: 1.2, y: yy, w: 6, h: 0.4,
      fontSize: 15, color: C.dark, fontFace: "Calibri", bold: true,
      valign: "middle", margin: 0
    });
    // Time pill
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 8.0, y: yy + 0.05, w: 0.9, h: 0.3,
      fill: { color: C.cream }
    });
    slide.addText(item.time, {
      x: 8.0, y: yy + 0.05, w: 0.9, h: 0.3,
      fontSize: 10, color: C.muted, fontFace: "Calibri",
      align: "center", valign: "middle", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 3: PROBLEM & LÖSUNG
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "1", "Problem & Lösung");
  addFooter(slide, 3, TOTAL);

  // Problem card
  addCard(slide, 0.5, 1.2, 4.2, 3.7, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.2, w: 4.2, h: 0.06,
    fill: { color: C.red }
  });
  slide.addText("❌  Das Problem", {
    x: 0.8, y: 1.35, w: 3.6, h: 0.4,
    fontSize: 16, color: C.red, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "Manuelle Bestellannahme per Telefon/WhatsApp", options: { bullet: true, breakLine: true, fontSize: 12 } },
    { text: "Fehlende Infos → Rückfragen → Zeitverlust", options: { bullet: true, breakLine: true, fontSize: 12 } },
    { text: "Keine einheitliche Preisberechnung", options: { bullet: true, breakLine: true, fontSize: 12 } },
    { text: "Kunde kann sich Torte nicht vorstellen", options: { bullet: true, breakLine: true, fontSize: 12 } },
    { text: "Keine 24/7 Erreichbarkeit", options: { bullet: true, fontSize: 12 } },
  ], {
    x: 0.8, y: 1.85, w: 3.7, h: 2.8,
    color: C.text, fontFace: "Calibri", paraSpaceAfter: 8, valign: "top", margin: 0
  });

  // Solution card
  addCard(slide, 5.3, 1.2, 4.2, 3.7, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.3, y: 1.2, w: 4.2, h: 0.06,
    fill: { color: C.green }
  });
  slide.addText("✅  Die Lösung: Kidstorte", {
    x: 5.6, y: 1.35, w: 3.6, h: 0.4,
    fontSize: 16, color: C.green, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "KI-Chatbot führt durch die Bestellung", options: { bullet: true, breakLine: true, fontSize: 12 } },
    { text: "Automatische Extraktion aller Details", options: { bullet: true, breakLine: true, fontSize: 12 } },
    { text: "Dynamische Preisberechnung mit RAG", options: { bullet: true, breakLine: true, fontSize: 12 } },
    { text: "KI-Vorschaubild der Torte in Echtzeit", options: { bullet: true, breakLine: true, fontSize: 12 } },
    { text: "24/7 verfügbar — kein Anruf nötig", options: { bullet: true, breakLine: true, fontSize: 12 } },
    { text: "PDF-Bestellung + E-Mail an Konditor", options: { bullet: true, fontSize: 12 } },
  ], {
    x: 5.6, y: 1.85, w: 3.7, h: 2.8,
    color: C.text, fontFace: "Calibri", paraSpaceAfter: 8, valign: "top", margin: 0
  });

  // Arrow between
  slide.addText("→", {
    x: 4.5, y: 2.5, w: 1, h: 0.8,
    fontSize: 36, color: C.primary, fontFace: "Georgia",
    align: "center", valign: "middle", margin: 0
  });
})();

// ============================================================
// SLIDE 4: TECH STACK
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "2", "Tech Stack");
  addFooter(slide, 4, TOTAL);

  const stacks = [
    { cat: "Backend", items: "FastAPI, Python 3.11, Pydantic", icon: "⚙️", color: C.blue },
    { cat: "KI / LLM", items: "OpenAI GPT-4o-mini, gpt-image-1", icon: "🧠", color: C.primary },
    { cat: "Vektordatenbank", items: "ChromaDB (RAG + Sessions)", icon: "🗄️", color: C.green },
    { cat: "Orchestrierung", items: "LangGraph (State Machine)", icon: "🔄", color: C.purple },
    { cat: "Monitoring", items: "LangSmith Tracing & Eval", icon: "📊", color: C.orange },
    { cat: "Frontend", items: "HTML/CSS/JS, SSE Streaming", icon: "💻", color: C.sage },
    { cat: "Datenbank", items: "SQLite (Bestellungen, Bewertungen)", icon: "💾", color: C.secondary },
    { cat: "Services", items: "E-Mail (SMTP), cal.com, PDF", icon: "📧", color: C.red },
  ];

  stacks.forEach((s, i) => {
    const col = i % 4;
    const row = Math.floor(i / 4);
    const cx = 0.5 + col * 2.35;
    const cy = 1.2 + row * 2.0;

    addCard(slide, cx, cy, 2.15, 1.7, C.card);

    slide.addText(s.icon, {
      x: cx + 0.15, y: cy + 0.15, w: 0.5, h: 0.5,
      fontSize: 22, align: "center", valign: "middle", margin: 0
    });
    slide.addText(s.cat, {
      x: cx + 0.65, y: cy + 0.15, w: 1.35, h: 0.35,
      fontSize: 12, color: s.color, fontFace: "Georgia", bold: true, valign: "middle", margin: 0
    });
    slide.addText(s.items, {
      x: cx + 0.15, y: cy + 0.7, w: 1.85, h: 0.85,
      fontSize: 10, color: C.muted, fontFace: "Calibri", valign: "top", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 5: ARCHITEKTUR ÜBERBLICK
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.dark };
  slide.addText("Architektur-Überblick", {
    x: 0.5, y: 0.3, w: 9, h: 0.6,
    fontSize: 28, color: C.textLight, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 0.95, w: 3, h: 0.04, fill: { color: C.primary }
  });
  addFooter(slide, 5, TOTAL);

  // Flow boxes
  const flow = [
    { label: "Kunde", sub: "Chat Widget", x: 0.3, color: C.accent },
    { label: "FastAPI", sub: "REST + SSE", x: 2.1, color: C.blue },
    { label: "Guardrail", sub: "Input-Filter", x: 3.9, color: C.red },
    { label: "Classify", sub: "Intent + Extract", x: 5.7, color: C.primary },
    { label: "Router", sub: "8 Intents", x: 7.5, color: C.purple },
  ];

  flow.forEach((f, i) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: f.x, y: 1.4, w: 1.6, h: 0.9,
      fill: { color: f.color }, shadow: makeShadow()
    });
    slide.addText(f.label, {
      x: f.x, y: 1.4, w: 1.6, h: 0.55,
      fontSize: 12, color: C.textLight, fontFace: "Calibri", bold: true,
      align: "center", valign: "bottom", margin: 0
    });
    slide.addText(f.sub, {
      x: f.x, y: 1.85, w: 1.6, h: 0.4,
      fontSize: 9, color: "FFFFFF", fontFace: "Calibri",
      align: "center", valign: "top", margin: 0, transparency: 30
    });
    // Arrow between
    if (i < flow.length - 1) {
      slide.addText("→", {
        x: f.x + 1.55, y: 1.5, w: 0.6, h: 0.7,
        fontSize: 20, color: C.accent, fontFace: "Georgia",
        align: "center", valign: "middle", margin: 0
      });
    }
  });

  // Intent branches
  const intents = [
    { label: "greeting", node: "greet()", color: C.sage },
    { label: "order", node: "extract → check → ask_next", color: C.green },
    { label: "price", node: "RAG → calculate_price()", color: C.blue },
    { label: "image", node: "generate_image()", color: C.orange },
    { label: "info", node: "RAG → answer_question()", color: C.purple },
    { label: "change", node: "update_order()", color: C.primary },
    { label: "finalize", node: "finalize_order()", color: C.red },
    { label: "offtopic", node: "redirect()", color: C.muted },
  ];

  intents.forEach((intent, i) => {
    const col = i % 4;
    const row = Math.floor(i / 4);
    const ix = 0.5 + col * 2.35;
    const iy = 2.75 + row * 1.15;

    slide.addShape(pres.shapes.RECTANGLE, {
      x: ix, y: iy, w: 2.15, h: 0.9,
      fill: { color: intent.color }, shadow: makeShadow(),
      transparency: 15
    });
    slide.addText(intent.label, {
      x: ix, y: iy, w: 2.15, h: 0.45,
      fontSize: 11, color: C.textLight, fontFace: "Consolas", bold: true,
      align: "center", valign: "bottom", margin: 0
    });
    slide.addText(intent.node, {
      x: ix, y: iy + 0.45, w: 2.15, h: 0.4,
      fontSize: 8, color: "FFFFFF", fontFace: "Calibri",
      align: "center", valign: "top", margin: 0, transparency: 25
    });
  });
})();

// ============================================================
// SLIDE 6: STATE MACHINE — AgentState
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "3", "AgentState — Das Herz der State Machine");
  addFooter(slide, 6, TOTAL);

  // Explanation
  slide.addText("Jeder Node bekommt den State, verarbeitet ihn, und gibt den aktualisierten State zurück.", {
    x: 0.5, y: 1.1, w: 9, h: 0.4,
    fontSize: 13, color: C.muted, fontFace: "Calibri", italic: true, margin: 0
  });

  // State fields - left column
  addCard(slide, 0.5, 1.7, 4.3, 3.3, C.card);
  slide.addText("Kern-Felder", {
    x: 0.7, y: 1.8, w: 3.9, h: 0.35,
    fontSize: 13, color: C.primary, fontFace: "Georgia", bold: true, margin: 0
  });
  const coreFields = [
    "session_id: str — Eindeutige Session-ID",
    "user_input: str — Aktuelle Kundennachricht",
    "messages: list — Gesprächsverlauf (max. 20)",
    "intent: str — Erkannter Intent (8 Typen)",
    "order_info: dict — Alle Bestelldetails",
    "order_complete: bool — Alle Pflichtfelder gefüllt?",
    "missing_fields: list — Noch fehlende Felder",
    "question_todo: dict — Feld-Status-Tracking",
    "response: str — Bot-Antwort an Kunden",
  ];
  slide.addText(
    coreFields.map((f, i) => ({
      text: f,
      options: { bullet: true, breakLine: i < coreFields.length - 1, fontSize: 10 }
    })),
    {
      x: 0.7, y: 2.2, w: 3.9, h: 2.6,
      color: C.text, fontFace: "Calibri", paraSpaceAfter: 4, valign: "top", margin: 0
    }
  );

  // OrderInfo fields - right column
  addCard(slide, 5.2, 1.7, 4.3, 3.3, C.card);
  slide.addText("OrderInfo — 13 Bestellfelder", {
    x: 5.4, y: 1.8, w: 3.9, h: 0.35,
    fontSize: 13, color: C.green, fontFace: "Georgia", bold: true, margin: 0
  });
  const orderFields = [
    "anlass — Geburtstag, Hochzeit, Taufe...",
    "gaeste — Anzahl der Gäste",
    "geschmack — Schokolade, Vanille, Erdbeere...",
    "form — rund, eckig, Herzform",
    "schichten — 1-4+ Stockwerke",
    "fuellung — Himbeere, Schoko, Vanille...",
    "dekoration — Fondant, Motivkuchen, Avatar...",
    "allergien — Gluten, Nüsse, Laktose, Keine",
    "beschriftung — Happy Birthday Max!",
    "abholung — Abholung oder Lieferung",
  ];
  slide.addText(
    orderFields.map((f, i) => ({
      text: f,
      options: { bullet: true, breakLine: i < orderFields.length - 1, fontSize: 10 }
    })),
    {
      x: 5.4, y: 2.2, w: 3.9, h: 2.6,
      color: C.text, fontFace: "Calibri", paraSpaceAfter: 3, valign: "top", margin: 0
    }
  );
})();

// ============================================================
// SLIDE 7: NODES DETAIL 1 — Guardrail + Classify
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "3", "Nodes im Detail — Guardrail & Classify");
  addFooter(slide, 7, TOTAL);

  // Guardrail
  addCard(slide, 0.5, 1.2, 4.3, 2.0, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.2, w: 0.08, h: 2.0, fill: { color: C.red }
  });
  slide.addText("🛡️  Node 0: Guardrail", {
    x: 0.75, y: 1.3, w: 3.8, h: 0.35,
    fontSize: 14, color: C.red, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "LLM-basierter Eingabefilter", options: { bullet: true, breakLine: true } },
    { text: "Blockiert: Beleidigungen, Jailbreaks, Spam", options: { bullet: true, breakLine: true } },
    { text: "Erlaubt: Deko-Wünsche (Ronaldo, Elsa, Figuren)", options: { bullet: true, breakLine: true } },
    { text: "Fail-Open: Bei Fehler → Nachricht durchlassen", options: { bullet: true } },
  ], {
    x: 0.75, y: 1.75, w: 3.8, h: 1.3,
    fontSize: 10, color: C.text, fontFace: "Calibri", paraSpaceAfter: 3, margin: 0
  });

  // Classify & Extract
  addCard(slide, 5.2, 1.2, 4.3, 2.0, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 1.2, w: 0.08, h: 2.0, fill: { color: C.primary }
  });
  slide.addText("🎯  Node 1: Classify & Extract", {
    x: 5.45, y: 1.3, w: 3.8, h: 0.35,
    fontSize: 14, color: C.primary, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "1 LLM-Call statt 2 → Kostenersparnis 50%", options: { bullet: true, breakLine: true } },
    { text: "Intent-Erkennung + Info-Extraktion kombiniert", options: { bullet: true, breakLine: true } },
    { text: "JSON-Output: {intent, extracted}", options: { bullet: true, breakLine: true } },
    { text: "Schutzlogik: \"Lieferung am Datum\" ≠ Abholung", options: { bullet: true } },
  ], {
    x: 5.45, y: 1.75, w: 3.8, h: 1.3,
    fontSize: 10, color: C.text, fontFace: "Calibri", paraSpaceAfter: 3, margin: 0
  });

  // Example box
  addCard(slide, 0.5, 3.5, 9.0, 1.6, C.cream);
  slide.addText("Beispiel — Combined Classify & Extract", {
    x: 0.7, y: 3.6, w: 8.6, h: 0.3,
    fontSize: 12, color: C.secondary, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: 'Kunde: ', options: { bold: true, breakLine: false } },
    { text: '"Schokoladentorte für 20 Leute, rund, 3 Schichten"', options: { italic: true, breakLine: true } },
    { text: 'LLM-Antwort: ', options: { bold: true, breakLine: false } },
    { text: '{"intent": "order", "extracted": {"geschmack": "Schokolade", "gaeste": "20", "form": "rund", "schichten": "3"}}', options: { fontFace: "Consolas", fontSize: 9, breakLine: false } },
  ], {
    x: 0.7, y: 3.95, w: 8.6, h: 1.0,
    fontSize: 11, color: C.text, fontFace: "Calibri", margin: 0
  });
})();

// ============================================================
// SLIDE 8: NODES DETAIL 2 — Order Flow
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "3", "Order-Flow — check_complete → ask_next → summarize");
  addFooter(slide, 8, TOTAL);

  // Flow diagram
  const steps = [
    { label: "extract_info", desc: "Infos parsen", color: C.blue, x: 0.3 },
    { label: "check_complete", desc: "Felder prüfen", color: C.green, x: 2.6 },
    { label: "ask_next", desc: "Nächste Frage", color: C.orange, x: 4.9 },
    { label: "summarize", desc: "Zusammenfassung", color: C.primary, x: 7.2 },
  ];

  steps.forEach((s, i) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: s.x, y: 1.2, w: 2.1, h: 0.75,
      fill: { color: s.color }, shadow: makeShadow()
    });
    slide.addText(s.label, {
      x: s.x, y: 1.2, w: 2.1, h: 0.45,
      fontSize: 11, color: C.textLight, fontFace: "Consolas", bold: true,
      align: "center", valign: "bottom", margin: 0
    });
    slide.addText(s.desc, {
      x: s.x, y: 1.6, w: 2.1, h: 0.3,
      fontSize: 9, color: C.textLight, fontFace: "Calibri",
      align: "center", valign: "top", margin: 0
    });
    if (i < steps.length - 1) {
      slide.addText("→", {
        x: s.x + 2.0, y: 1.25, w: 0.7, h: 0.65,
        fontSize: 20, color: C.primary, align: "center", valign: "middle", margin: 0
      });
    }
  });

  // question_todo explanation
  addCard(slide, 0.5, 2.3, 4.3, 2.6, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 2.3, w: 0.08, h: 2.6, fill: { color: C.blue }
  });
  slide.addText("question_todo — Feld-Tracking", {
    x: 0.75, y: 2.4, w: 3.8, h: 0.3,
    fontSize: 13, color: C.blue, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: '"pending" — Noch nicht gefragt', options: { bullet: true, breakLine: true } },
    { text: '"asked" — Berater hat gefragt, wartet auf Antwort', options: { bullet: true, breakLine: true } },
    { text: '"answered" — Kunde hat geantwortet', options: { bullet: true, breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "Priorität: asked-Felder zuerst, dann pending", options: { bold: true, breakLine: true } },
    { text: "Verhindert doppelte Fragen!", options: { italic: true } },
  ], {
    x: 0.75, y: 2.8, w: 3.8, h: 1.9,
    fontSize: 11, color: C.text, fontFace: "Calibri", paraSpaceAfter: 3, margin: 0
  });

  // check_complete logic
  addCard(slide, 5.2, 2.3, 4.3, 2.6, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 2.3, w: 0.08, h: 2.6, fill: { color: C.green }
  });
  slide.addText("check_complete — Validierung", {
    x: 5.45, y: 2.4, w: 3.8, h: 0.3,
    fontSize: 13, color: C.green, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "Prüft 10 Pflichtfelder:", options: { bold: true, breakLine: true } },
    { text: "anlass, gaeste, geschmack, form, schichten,", options: { breakLine: true, fontSize: 10 } },
    { text: "fuellung, dekoration, allergien, beschriftung, abholung", options: { breakLine: true, fontSize: 10 } },
    { text: "", options: { breakLine: true } },
    { text: 'Filtert vage Antworten: "ja", "ok", "deko"', options: { bullet: true, breakLine: true } },
    { text: "→ Feld wird als ungefüllt markiert", options: { bullet: true, breakLine: true } },
    { text: "→ Bot fragt nochmal konkreter nach", options: { bullet: true } },
  ], {
    x: 5.45, y: 2.8, w: 3.8, h: 1.9,
    fontSize: 11, color: C.text, fontFace: "Calibri", paraSpaceAfter: 2, margin: 0
  });
})();

// ============================================================
// SLIDE 9: RAG SYSTEM
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "4", "RAG — Retrieval Augmented Generation");
  addFooter(slide, 9, TOTAL);

  slide.addText("Wissen aus Dokumenten statt Halluzination", {
    x: 0.5, y: 1.1, w: 9, h: 0.35,
    fontSize: 13, color: C.muted, fontFace: "Calibri", italic: true, margin: 0
  });

  // RAG Flow
  const ragSteps = [
    { label: "Dokumente", desc: "products.md\npricing_rules.md\nprocess.md", x: 0.3, color: C.secondary },
    { label: "Chunking", desc: "Split by\n## Headers", x: 2.55, color: C.blue },
    { label: "Embedding", desc: "text-embedding\n-3-small", x: 4.8, color: C.primary },
    { label: "ChromaDB", desc: "Vektor-\nDatenbank", x: 7.05, color: C.green },
  ];

  ragSteps.forEach((s, i) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: s.x, y: 1.65, w: 2.0, h: 1.0,
      fill: { color: s.color }, shadow: makeShadow()
    });
    slide.addText(s.label, {
      x: s.x, y: 1.65, w: 2.0, h: 0.45,
      fontSize: 12, color: C.textLight, fontFace: "Calibri", bold: true,
      align: "center", valign: "bottom", margin: 0
    });
    slide.addText(s.desc, {
      x: s.x, y: 2.1, w: 2.0, h: 0.5,
      fontSize: 9, color: C.textLight, fontFace: "Calibri",
      align: "center", valign: "top", margin: 0
    });
    if (i < ragSteps.length - 1) {
      slide.addText("→", {
        x: s.x + 1.9, y: 1.8, w: 0.7, h: 0.65,
        fontSize: 18, color: C.primary, align: "center", valign: "middle", margin: 0
      });
    }
  });

  // Retrieval flow
  addCard(slide, 0.5, 3.0, 9.0, 2.0, C.card);
  slide.addText("Retrieval bei Kundenanfrage", {
    x: 0.7, y: 3.1, w: 8.6, h: 0.3,
    fontSize: 14, color: C.primary, fontFace: "Georgia", bold: true, margin: 0
  });

  const retrievalSteps = [
    { num: "1", text: "Kundenanfrage wird embedded (1536-dim Vektor)" },
    { num: "2", text: "Top-5 ähnlichste Chunks aus ChromaDB abgerufen" },
    { num: "3", text: "Chunks als Kontext dem LLM mitgegeben" },
    { num: "4", text: "LLM antwortet basierend auf echten Daten (kein Halluzinieren!)" },
  ];

  retrievalSteps.forEach((s, i) => {
    const sx = 0.7 + i * 2.2;
    slide.addShape(pres.shapes.OVAL, {
      x: sx, y: 3.55, w: 0.3, h: 0.3,
      fill: { color: C.primary }
    });
    slide.addText(s.num, {
      x: sx, y: 3.55, w: 0.3, h: 0.3,
      fontSize: 10, color: C.textLight, fontFace: "Calibri", bold: true,
      align: "center", valign: "middle", margin: 0
    });
    slide.addText(s.text, {
      x: sx + 0.35, y: 3.5, w: 1.75, h: 0.5,
      fontSize: 10, color: C.text, fontFace: "Calibri", valign: "middle", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 10: LLM INTEGRATION
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "4", "LLM-Integration — OpenAI GPT-4o-mini");
  addFooter(slide, 10, TOTAL);

  // Left: LLM Calls
  addCard(slide, 0.5, 1.2, 4.3, 3.7, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.2, w: 0.08, h: 3.7, fill: { color: C.blue }
  });
  slide.addText("LLM-Aufrufe im System", {
    x: 0.75, y: 1.3, w: 3.8, h: 0.35,
    fontSize: 14, color: C.blue, fontFace: "Georgia", bold: true, margin: 0
  });

  const calls = [
    { name: "Guardrail", model: "gpt-4o-mini", temp: "0", purpose: "Input-Filter" },
    { name: "Classify+Extract", model: "gpt-4o-mini", temp: "0", purpose: "Intent + Daten" },
    { name: "Ask Next", model: "gpt-4o-mini", temp: "0.6", purpose: "Nächste Frage" },
    { name: "Calculate Price", model: "gpt-4o-mini", temp: "0", purpose: "Preisberechnung" },
    { name: "Answer Question", model: "gpt-4o-mini", temp: "0.3", purpose: "Info-Antwort" },
    { name: "Image Prompt", model: "gpt-4o-mini", temp: "0", purpose: "Bild-Beschreibung" },
  ];

  calls.forEach((c, i) => {
    const cy = 1.8 + i * 0.42;
    slide.addText(`${c.name}`, {
      x: 0.75, y: cy, w: 1.5, h: 0.35,
      fontSize: 10, color: C.text, fontFace: "Calibri", bold: true, valign: "middle", margin: 0
    });
    slide.addText(`T=${c.temp}`, {
      x: 2.3, y: cy, w: 0.6, h: 0.35,
      fontSize: 9, color: C.muted, fontFace: "Consolas", valign: "middle", margin: 0
    });
    slide.addText(c.purpose, {
      x: 2.95, y: cy, w: 1.6, h: 0.35,
      fontSize: 9, color: C.muted, fontFace: "Calibri", valign: "middle", margin: 0
    });
  });

  // Right: Optimierungen
  addCard(slide, 5.2, 1.2, 4.3, 3.7, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 1.2, w: 0.08, h: 3.7, fill: { color: C.green }
  });
  slide.addText("Optimierungen", {
    x: 5.45, y: 1.3, w: 3.8, h: 0.35,
    fontSize: 14, color: C.green, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "Combined Call:", options: { bold: true, breakLine: true } },
    { text: "Intent + Extraktion in 1 LLM-Call → 50% weniger API-Kosten", options: { breakLine: true, fontSize: 10 } },
    { text: "", options: { breakLine: true } },
    { text: "Retry-Logik:", options: { bold: true, breakLine: true } },
    { text: "Exponential Backoff bei Rate Limits (5s → 10s → 20s)", options: { breakLine: true, fontSize: 10 } },
    { text: "", options: { breakLine: true } },
    { text: "JSON Self-Correction:", options: { bold: true, breakLine: true } },
    { text: "Fehlerhaftes JSON → LLM bekommt Fehlermeldung → korrigiert sich selbst", options: { breakLine: true, fontSize: 10 } },
    { text: "", options: { breakLine: true } },
    { text: "Response Cache:", options: { bold: true, breakLine: true } },
    { text: "LRU-Cache (200 Einträge, 1h TTL) für wiederholte Anfragen", options: { breakLine: true, fontSize: 10 } },
    { text: "", options: { breakLine: true } },
    { text: "Prompt Engineering:", options: { bold: true, breakLine: true } },
    { text: "Hot-Reload aus YAML — Prompts ändern ohne Neustart", options: { fontSize: 10 } },
  ], {
    x: 5.45, y: 1.75, w: 3.8, h: 2.9,
    color: C.text, fontFace: "Calibri", paraSpaceAfter: 1, valign: "top", margin: 0
  });
})();

// ============================================================
// SLIDE 11: BILDGENERIERUNG
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.dark };
  slide.addText("KI-Bildgenerierung — Tortenvision", {
    x: 0.5, y: 0.3, w: 9, h: 0.6,
    fontSize: 28, color: C.textLight, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 0.95, w: 3, h: 0.04, fill: { color: C.accent }
  });
  addFooter(slide, 11, TOTAL);

  // Two-image concept
  addCard(slide, 0.5, 1.3, 4.3, 1.8, "3D3028");
  slide.addText("🎂  Außenansicht", {
    x: 0.7, y: 1.4, w: 3.9, h: 0.35,
    fontSize: 14, color: C.accent, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "Vollständige Torte mit Dekoration", options: { bullet: true, breakLine: true } },
    { text: "Form, Farbe, Schichten, Fondant", options: { bullet: true, breakLine: true } },
    { text: "Figuren & Motive (Elsa, Ronaldo...)", options: { bullet: true } },
  ], {
    x: 0.7, y: 1.85, w: 3.9, h: 1.1,
    fontSize: 11, color: C.textLight, fontFace: "Calibri", paraSpaceAfter: 3, margin: 0
  });

  addCard(slide, 5.2, 1.3, 4.3, 1.8, "3D3028");
  slide.addText("🔪  Querschnitt", {
    x: 5.4, y: 1.4, w: 3.9, h: 0.35,
    fontSize: 14, color: C.accent, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "Anschnittbild mit sichtbaren Schichten", options: { bullet: true, breakLine: true } },
    { text: "Füllung zwischen den Etagen erkennbar", options: { bullet: true, breakLine: true } },
    { text: "Farbcodierung basierend auf Geschmack", options: { bullet: true } },
  ], {
    x: 5.4, y: 1.85, w: 3.9, h: 1.1,
    fontSize: 11, color: C.textLight, fontFace: "Calibri", paraSpaceAfter: 3, margin: 0
  });

  // Provider chain
  addCard(slide, 0.5, 3.4, 9.0, 1.5, "3D3028");
  slide.addText("Provider-Kette & Referenz-Matching", {
    x: 0.7, y: 3.5, w: 8.6, h: 0.35,
    fontSize: 14, color: C.accent, fontFace: "Georgia", bold: true, margin: 0
  });

  const providers = [
    { label: "gpt-image-1", desc: "Primary\n120s Timeout", color: C.primary, x: 0.7 },
    { label: "HuggingFace", desc: "Fallback\nDiffusers API", color: C.blue, x: 3.0 },
    { label: "Referenz-Match", desc: "Vision-Analyse\n60+ Portfolio", color: C.green, x: 5.3 },
    { label: "Auto-Save", desc: "Bild → Portfolio\nfür Matching", color: C.purple, x: 7.6 },
  ];

  providers.forEach((p, i) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: p.x, y: 4.0, w: 1.9, h: 0.75,
      fill: { color: p.color }, shadow: makeShadow()
    });
    slide.addText(p.label, {
      x: p.x, y: 4.0, w: 1.9, h: 0.38,
      fontSize: 10, color: C.textLight, fontFace: "Calibri", bold: true,
      align: "center", valign: "bottom", margin: 0
    });
    slide.addText(p.desc, {
      x: p.x, y: 4.38, w: 1.9, h: 0.35,
      fontSize: 8, color: C.textLight, fontFace: "Calibri",
      align: "center", valign: "top", margin: 0
    });
    if (i < providers.length - 1) {
      slide.addText("→", {
        x: p.x + 1.85, y: 4.05, w: 0.5, h: 0.65,
        fontSize: 16, color: C.accent, align: "center", valign: "middle", margin: 0
      });
    }
  });
})();

// ============================================================
// SLIDE 12: SESSION MANAGEMENT
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "5", "Session Management & Datenbank");
  addFooter(slide, 12, TOTAL);

  // Session
  addCard(slide, 0.5, 1.2, 4.3, 3.7, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.2, w: 0.08, h: 3.7, fill: { color: C.purple }
  });
  slide.addText("Session-Persistenz (ChromaDB)", {
    x: 0.75, y: 1.3, w: 3.8, h: 0.35,
    fontSize: 14, color: C.purple, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "Cookie-basiert: cake_session_id", options: { bullet: true, breakLine: true } },
    { text: "ChromaDB = Vektordatenbank + Session Store", options: { bullet: true, breakLine: true } },
    { text: "Session-Daten als JSON serialisiert", options: { bullet: true, breakLine: true } },
    { text: "Automatischer Cleanup nach 24h TTL", options: { bullet: true, breakLine: true } },
    { text: "Metadata: created, last_accessed, message_count", options: { bullet: true, breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "Gespeicherte Felder:", options: { bold: true, breakLine: true } },
    { text: "messages, order_info, question_todo, intent, order_complete, calculated_price, image_url, _image_gen_failed", options: { fontSize: 9, fontFace: "Consolas" } },
  ], {
    x: 0.75, y: 1.75, w: 3.8, h: 3.0,
    fontSize: 11, color: C.text, fontFace: "Calibri", paraSpaceAfter: 3, valign: "top", margin: 0
  });

  // Database
  addCard(slide, 5.2, 1.2, 4.3, 3.7, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 1.2, w: 0.08, h: 3.7, fill: { color: C.blue }
  });
  slide.addText("SQLite — Bestellungen & Bewertungen", {
    x: 5.45, y: 1.3, w: 3.8, h: 0.35,
    fontSize: 14, color: C.blue, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "Tabelle: orders", options: { bold: true, breakLine: true } },
    { text: "id, session_id, order_info (JSON), customer_name, customer_email, phone, street, plz, city, liefertermin, total_price, status, created_at", options: { fontSize: 9, fontFace: "Consolas", breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "Tabelle: ratings", options: { bold: true, breakLine: true } },
    { text: "id, order_id (FK), rating (1-5), comment, created_at", options: { fontSize: 9, fontFace: "Consolas", breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "WAL-Modus für schnelle Schreibzugriffe", options: { bullet: true, breakLine: true } },
    { text: "Kapazitätsprüfung: max_orders_per_day", options: { bullet: true, breakLine: true } },
    { text: "Status-Management: neu → in Bearbeitung → fertig", options: { bullet: true } },
  ], {
    x: 5.45, y: 1.75, w: 3.8, h: 3.0,
    fontSize: 11, color: C.text, fontFace: "Calibri", paraSpaceAfter: 2, valign: "top", margin: 0
  });
})();

// ============================================================
// SLIDE 13: SERVICES
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "5", "Services — E-Mail, Kalender, PDF");
  addFooter(slide, 13, TOTAL);

  const services = [
    {
      icon: "📧", title: "E-Mail Service",
      color: C.primary,
      items: ["SMTP-Integration (GMX)", "HTML-E-Mail an Designer", "Bestätigung an Kunden", "Graceful: Ohne SMTP → nur Log"]
    },
    {
      icon: "📅", title: "Kalender (cal.com)",
      color: C.blue,
      items: ["API v2 Integration", "Deutsche Datumsformate parsen", "Verfügbarkeit prüfen", "Alternativtermine vorschlagen"]
    },
    {
      icon: "📄", title: "PDF-Generierung",
      color: C.green,
      items: ["ReportLab mit Kidstorte-Branding", "Bestellzusammenfassung", "Kundenadresse + Vorschaubild", "Download über /order/{id}/pdf"]
    },
    {
      icon: "💰", title: "Cost Optimizer",
      color: C.orange,
      items: ["Token-Tracking pro Modell", "LRU Response-Cache (200 Einträge)", "SHA256-basiertes Caching", "Kostenabrechnung in USD"]
    },
  ];

  services.forEach((s, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const sx = 0.5 + col * 4.7;
    const sy = 1.2 + row * 2.1;

    addCard(slide, sx, sy, 4.3, 1.8, C.card);
    slide.addShape(pres.shapes.RECTANGLE, {
      x: sx, y: sy, w: 0.08, h: 1.8, fill: { color: s.color }
    });
    slide.addText(`${s.icon}  ${s.title}`, {
      x: sx + 0.2, y: sy + 0.1, w: 3.9, h: 0.35,
      fontSize: 13, color: s.color, fontFace: "Georgia", bold: true, margin: 0
    });
    slide.addText(
      s.items.map((item, j) => ({
        text: item,
        options: { bullet: true, breakLine: j < s.items.length - 1, fontSize: 10 }
      })),
      {
        x: sx + 0.2, y: sy + 0.5, w: 3.9, h: 1.2,
        color: C.text, fontFace: "Calibri", paraSpaceAfter: 2, valign: "top", margin: 0
      }
    );
  });
})();

// ============================================================
// SLIDE 14: FRONTEND & UX
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "6", "Frontend & User Experience");
  addFooter(slide, 14, TOTAL);

  // Chat Widget description
  addCard(slide, 0.5, 1.2, 4.3, 3.7, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.2, w: 0.08, h: 3.7, fill: { color: C.primary }
  });
  slide.addText("Chat-Widget", {
    x: 0.75, y: 1.3, w: 3.8, h: 0.35,
    fontSize: 14, color: C.primary, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "SSE-Streaming (Server-Sent Events)", options: { bullet: true, breakLine: true, bold: true } },
    { text: "Wort-für-Wort Anzeige (30ms Delay)", options: { bullet: true, breakLine: true } },
    { text: "→ Natürliches \"Tipp\"-Gefühl", options: { breakLine: true, italic: true } },
    { text: "", options: { breakLine: true } },
    { text: "Dynamisches Formular:", options: { bold: true, breakLine: true } },
    { text: "Abholung → Name, Tel, E-Mail", options: { bullet: true, breakLine: true } },
    { text: "Lieferung → + Straße, PLZ, Stadt", options: { bullet: true, breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "Echtzeit-Bestellübersicht (rechte Seite)", options: { bullet: true, breakLine: true } },
    { text: "Bild-Karussell: Außen + Querschnitt", options: { bullet: true, breakLine: true } },
    { text: "Referenzbild aus Portfolio", options: { bullet: true } },
  ], {
    x: 0.75, y: 1.75, w: 3.8, h: 3.0,
    fontSize: 11, color: C.text, fontFace: "Calibri", paraSpaceAfter: 2, valign: "top", margin: 0
  });

  // Admin Panel
  addCard(slide, 5.2, 1.2, 4.3, 3.7, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 1.2, w: 0.08, h: 3.7, fill: { color: C.secondary }
  });
  slide.addText("Admin Panel", {
    x: 5.45, y: 1.3, w: 3.8, h: 0.35,
    fontSize: 14, color: C.secondary, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "Passwortgeschützt (Cookie-Auth)", options: { bullet: true, breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "Dashboard:", options: { bold: true, breakLine: true } },
    { text: "Aktive Sessions, Bestellungen, Statistiken", options: { bullet: true, breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "Prompt-Editor:", options: { bold: true, breakLine: true } },
    { text: "System-Prompts live bearbeiten", options: { bullet: true, breakLine: true } },
    { text: "Hot-Reload ohne Neustart!", options: { bullet: true, breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "Bestell-Management:", options: { bold: true, breakLine: true } },
    { text: "Status ändern, Bewertungen lesen", options: { bullet: true, breakLine: true } },
    { text: "PDF generieren, Sessions verwalten", options: { bullet: true } },
  ], {
    x: 5.45, y: 1.75, w: 3.8, h: 3.0,
    fontSize: 11, color: C.text, fontFace: "Calibri", paraSpaceAfter: 1, valign: "top", margin: 0
  });
})();

// ============================================================
// SLIDE 15: API ENDPOINTS
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "6", "REST API — 20+ Endpoints");
  addFooter(slide, 15, TOTAL);

  const endpoints = [
    [
      { text: "Endpoint", options: { bold: true, color: "FFFFFF", fill: { color: C.dark } } },
      { text: "Methode", options: { bold: true, color: "FFFFFF", fill: { color: C.dark } } },
      { text: "Beschreibung", options: { bold: true, color: "FFFFFF", fill: { color: C.dark } } },
    ],
    ["/api/chat", "POST", "Chat-Nachricht senden"],
    ["/api/chat/stream", "POST", "SSE Streaming-Antwort"],
    ["/api/generate-image", "POST", "Bild generieren"],
    ["/api/submit-order", "POST", "Bestellung abschicken"],
    ["/api/reset", "POST", "Session zurücksetzen"],
    ["/api/state", "GET", "Debug: Session-State"],
    ["/api/metrics", "GET", "Token, Latenz, Kosten"],
    ["/api/availability", "GET", "Kalender-Kapazität"],
    ["/order/{id}/pdf", "GET", "Bestell-PDF generieren"],
    ["/admin", "GET", "Admin Dashboard"],
    ["/admin/prompts", "POST", "Prompts live bearbeiten"],
    ["/bewertung", "GET/POST", "Kunden-Bewertung"],
  ];

  slide.addTable(endpoints, {
    x: 0.5, y: 1.15, w: 9.0,
    fontSize: 10, fontFace: "Calibri",
    border: { pt: 0.5, color: C.cream },
    colW: [2.5, 1.2, 5.3],
    rowH: [0.32, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
    autoPage: false,
  });
})();

// ============================================================
// SLIDE 16: MONITORING & TRACING
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "7", "Monitoring & Tracing — LangSmith");
  addFooter(slide, 16, TOTAL);

  // LangSmith
  addCard(slide, 0.5, 1.2, 5.8, 2.0, C.card);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.2, w: 0.08, h: 2.0, fill: { color: C.orange }
  });
  slide.addText("LangSmith Integration", {
    x: 0.75, y: 1.3, w: 5.3, h: 0.35,
    fontSize: 14, color: C.orange, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "@trace_node(\"name\")", options: { fontFace: "Consolas", bold: true, breakLine: true, fontSize: 10 } },
    { text: "Jeder Node wird automatisch getraced", options: { breakLine: true } },
    { text: "", options: { breakLine: true } },
    { text: "Trackt: Inputs, Outputs, Dauer, Tokens, Kosten", options: { bullet: true, breakLine: true } },
    { text: "Trace-Hierarchie: Run → Node → LLM-Call", options: { bullet: true, breakLine: true } },
    { text: "Graceful: Ohne API-Key → Tracing deaktiviert", options: { bullet: true } },
  ], {
    x: 0.75, y: 1.75, w: 5.3, h: 1.3,
    fontSize: 11, color: C.text, fontFace: "Calibri", paraSpaceAfter: 2, valign: "top", margin: 0
  });

  // Metrics box
  addCard(slide, 6.6, 1.2, 2.9, 2.0, C.card);
  slide.addText("📊  Metriken", {
    x: 6.8, y: 1.3, w: 2.5, h: 0.3,
    fontSize: 12, color: C.green, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addText([
    { text: "Requests/Errors", options: { bullet: true, breakLine: true } },
    { text: "Latenz (P50/P95/P99)", options: { bullet: true, breakLine: true } },
    { text: "Tokens (in/out)", options: { bullet: true, breakLine: true } },
    { text: "Kosten in USD", options: { bullet: true, breakLine: true } },
    { text: "Uptime", options: { bullet: true } },
  ], {
    x: 6.8, y: 1.65, w: 2.5, h: 1.4,
    fontSize: 10, color: C.text, fontFace: "Calibri", paraSpaceAfter: 2, valign: "top", margin: 0
  });

  // Error handling
  addCard(slide, 0.5, 3.5, 9.0, 1.5, C.card);
  slide.addText("Error Handling — Robustheit", {
    x: 0.7, y: 3.6, w: 8.6, h: 0.3,
    fontSize: 14, color: C.red, fontFace: "Georgia", bold: true, margin: 0
  });

  const errorCols = [
    { title: "@retry_on_transient", desc: "Exponential Backoff\n3 Retries bei Rate Limit", color: C.primary },
    { title: "@safe_node", desc: "Fallback-Response\nbei Node-Fehler", color: C.blue },
    { title: "parse_llm_json", desc: "JSON Self-Correction\nmit LLM-Retry", color: C.green },
    { title: "Custom Exceptions", desc: "LLMError, RAGError\nSessionError", color: C.orange },
  ];

  errorCols.forEach((e, i) => {
    const ex = 0.7 + i * 2.2;
    slide.addShape(pres.shapes.OVAL, {
      x: ex + 0.6, y: 4.0, w: 0.3, h: 0.3,
      fill: { color: e.color }
    });
    slide.addText(e.title, {
      x: ex, y: 4.35, w: 2.0, h: 0.25,
      fontSize: 9, color: e.color, fontFace: "Consolas", bold: true,
      align: "center", valign: "middle", margin: 0
    });
    slide.addText(e.desc, {
      x: ex, y: 4.6, w: 2.0, h: 0.35,
      fontSize: 8, color: C.muted, fontFace: "Calibri",
      align: "center", valign: "top", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 17: PROMPT ENGINEERING
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "7", "Prompt Engineering — YAML-basiert");
  addFooter(slide, 17, TOTAL);

  slide.addText("Alle Prompts in einer YAML-Datei — Hot-Reload ohne Server-Neustart", {
    x: 0.5, y: 1.1, w: 9, h: 0.35,
    fontSize: 13, color: C.muted, fontFace: "Calibri", italic: true, margin: 0
  });

  const prompts = [
    { name: "classify_intent", lines: "~100 Zeilen", desc: "Intent-Erkennung mit Edge Cases, Tippfehler, Emojis, Bestätigungen", color: C.primary },
    { name: "extract_info", lines: "~65 Zeilen", desc: "Feld-Extraktion mit Negationen, Mehrfach-Info, Tippfehler-Korrektur", color: C.blue },
    { name: "ask_next", lines: "~30 Zeilen", desc: "Smalltalk, Persönlichkeit, Warmherzigkeit, Varianz", color: C.green },
    { name: "calculate_price", lines: "~45 Zeilen", desc: "Preislogik: Größe × Geschmack + Extras + Lieferung", color: C.orange },
    { name: "answer_question", lines: "~25 Zeilen", desc: "RAG-basierte Antworten, Produktwissen integriert", color: C.purple },
    { name: "image_description", lines: "~5 Zeilen", desc: "Visuelle Beschreibung für Bildgenerierung", color: C.sage },
  ];

  prompts.forEach((p, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const px = 0.5 + col * 4.7;
    const py = 1.65 + row * 1.2;

    addCard(slide, px, py, 4.3, 1.0, C.card);
    slide.addShape(pres.shapes.RECTANGLE, {
      x: px, y: py, w: 0.08, h: 1.0, fill: { color: p.color }
    });
    slide.addText(p.name, {
      x: px + 0.2, y: py + 0.05, w: 2.5, h: 0.3,
      fontSize: 11, color: p.color, fontFace: "Consolas", bold: true, margin: 0
    });
    slide.addText(p.lines, {
      x: px + 2.8, y: py + 0.05, w: 1.3, h: 0.3,
      fontSize: 9, color: C.muted, fontFace: "Calibri", align: "right", margin: 0
    });
    slide.addText(p.desc, {
      x: px + 0.2, y: py + 0.4, w: 3.9, h: 0.5,
      fontSize: 10, color: C.text, fontFace: "Calibri", valign: "top", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 18: LIVE DEMO INTRO
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.dark };
  addFooter(slide, 18, TOTAL);

  slide.addText("LIVE DEMO", {
    x: 0, y: 1.2, w: 10, h: 1.2,
    fontSize: 54, color: C.textLight, fontFace: "Georgia", bold: true,
    align: "center", charSpacing: 10, margin: 0
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 3.5, y: 2.5, w: 3, h: 0.04, fill: { color: C.primary }
  });
  slide.addText("Bestellprozess von A bis Z", {
    x: 0, y: 2.8, w: 10, h: 0.6,
    fontSize: 20, color: C.accent, fontFace: "Calibri",
    align: "center", margin: 0
  });

  // Demo steps
  const demoSteps = [
    "Begrüßung & Bestellstart",
    "Felder-Erfassung im Dialog",
    "KI-Vorschaubild generieren",
    "Preisberechnung mit RAG",
    "Bestellung abschicken",
    "Admin Panel & Monitoring",
  ];
  demoSteps.forEach((s, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const dx = 1.0 + col * 2.8;
    const dy = 3.6 + row * 0.65;

    slide.addShape(pres.shapes.OVAL, {
      x: dx, y: dy + 0.05, w: 0.3, h: 0.3,
      fill: { color: C.primary }
    });
    slide.addText(String(i + 1), {
      x: dx, y: dy + 0.05, w: 0.3, h: 0.3,
      fontSize: 10, color: C.textLight, fontFace: "Calibri", bold: true,
      align: "center", valign: "middle", margin: 0
    });
    slide.addText(s, {
      x: dx + 0.4, y: dy, w: 2.2, h: 0.4,
      fontSize: 12, color: C.textLight, fontFace: "Calibri", valign: "middle", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 19: DEMO — Gesprächsbeispiel
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "8", "Demo — Beispiel-Dialog");
  addFooter(slide, 19, TOTAL);

  const dialog = [
    { who: "Bot", msg: "Willkommen bei Kidstorte! Für welchen Anlass darf der Kuchen sein?", color: C.primary },
    { who: "Kunde", msg: "Geburtstag für meinen Sohn, er wird 5, ca. 20 Gäste", color: C.blue },
    { who: "Bot", msg: "Oh wie schön! Welche Geschmacksrichtung mag er am liebsten?", color: C.primary },
    { who: "Kunde", msg: "Schokolade, rund, 3 Schichten, Fondant blau mit Spiderman", color: C.blue },
    { who: "Bot", msg: "Super! Welche Füllung darf es sein?", color: C.primary },
    { who: "Kunde", msg: "1:Schoko, 2:Vanille, 3:Erdbeere, keine Allergien, Happy Birthday Noah!", color: C.blue },
    { who: "Bot", msg: "Alles notiert! Abholen oder liefern? → Bestellung komplett!", color: C.primary },
  ];

  dialog.forEach((d, i) => {
    const yy = 1.15 + i * 0.55;
    const isBot = d.who === "Bot";
    const msgX = isBot ? 0.5 : 2.5;
    const msgW = isBot ? 7.0 : 7.0;

    slide.addShape(pres.shapes.RECTANGLE, {
      x: msgX, y: yy, w: msgW, h: 0.45,
      fill: { color: isBot ? C.cream : "E8F0FE" },
      shadow: makeShadow()
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: msgX, y: yy, w: 0.06, h: 0.45,
      fill: { color: d.color }
    });
    slide.addText(`${d.who}:  ${d.msg}`, {
      x: msgX + 0.15, y: yy, w: msgW - 0.3, h: 0.45,
      fontSize: 10, color: C.text, fontFace: "Calibri", valign: "middle", margin: 0
    });
  });

  // Result summary
  addCard(slide, 0.5, 5.1 - 0.85, 9.0, 0.7, C.card);
  slide.addText("→ 10 Felder in 4 Nachrichten erfasst — Intent-Erkennung + Multi-Field-Extraktion in Aktion!", {
    x: 0.7, y: 5.1 - 0.85, w: 8.6, h: 0.7,
    fontSize: 12, color: C.green, fontFace: "Calibri", bold: true, italic: true,
    valign: "middle", margin: 0
  });
})();

// ============================================================
// SLIDE 20: DEMO — Node-Aktivierung
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "8", "Demo — Was passiert hinter den Kulissen?");
  addFooter(slide, 20, TOTAL);

  // Timeline
  const timeline = [
    { step: "1", node: "Guardrail", action: "Input OK → weiter", time: "~200ms", color: C.red },
    { step: "2", node: "Classify+Extract", action: "intent=order, 4 Felder extrahiert", time: "~800ms", color: C.primary },
    { step: "3", node: "check_complete", action: "6 Felder fehlen noch", time: "~10ms", color: C.green },
    { step: "4", node: "ask_next", action: "Frage nach Geschmack", time: "~600ms", color: C.orange },
    { step: "5", node: "Session Save", action: "State in ChromaDB gespeichert", time: "~50ms", color: C.purple },
    { step: "6", node: "SSE Stream", action: "Antwort Wort-für-Wort an Frontend", time: "~500ms", color: C.blue },
  ];

  timeline.forEach((t, i) => {
    const yy = 1.2 + i * 0.65;

    // Step circle
    slide.addShape(pres.shapes.OVAL, {
      x: 0.6, y: yy + 0.08, w: 0.4, h: 0.4,
      fill: { color: t.color }
    });
    slide.addText(t.step, {
      x: 0.6, y: yy + 0.08, w: 0.4, h: 0.4,
      fontSize: 12, color: C.textLight, fontFace: "Calibri", bold: true,
      align: "center", valign: "middle", margin: 0
    });

    // Connector line (except last)
    if (i < timeline.length - 1) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: 0.78, y: yy + 0.48, w: 0.04, h: 0.2,
        fill: { color: C.cream }
      });
    }

    // Node name
    slide.addText(t.node, {
      x: 1.2, y: yy, w: 2.2, h: 0.55,
      fontSize: 13, color: t.color, fontFace: "Consolas", bold: true,
      valign: "middle", margin: 0
    });

    // Action
    slide.addText(t.action, {
      x: 3.5, y: yy, w: 4.0, h: 0.55,
      fontSize: 11, color: C.text, fontFace: "Calibri",
      valign: "middle", margin: 0
    });

    // Time
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 8.0, y: yy + 0.1, w: 1.2, h: 0.35,
      fill: { color: C.cream }
    });
    slide.addText(t.time, {
      x: 8.0, y: yy + 0.1, w: 1.2, h: 0.35,
      fontSize: 10, color: C.muted, fontFace: "Consolas",
      align: "center", valign: "middle", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 21: HERAUSFORDERUNGEN
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "9", "Herausforderungen & Lösungen");
  addFooter(slide, 21, TOTAL);

  const challenges = [
    {
      problem: "LLM halluziniert Bestelldetails",
      solution: "Strikte Prompt-Regeln: \"Extrahiere NUR was der Kunde WÖRTLICH gesagt hat!\"",
      color: C.red
    },
    {
      problem: "\"Lieferung am 28.03\" ändert Abholung",
      solution: "Regex-Guard + Prompt-Schutz: Datum ≠ Abholungswechsel",
      color: C.orange
    },
    {
      problem: "Rate Limits bei 5 RPM",
      solution: "Exponential Backoff (5s → 10s → 20s) + Combined Calls",
      color: C.blue
    },
    {
      problem: "Content Moderation blockt Charaktere",
      solution: "Fallback-Prompt ohne geschützte Namen + HuggingFace",
      color: C.purple
    },
    {
      problem: "PDF-Preis ≠ Chat-Preis",
      solution: "calculated_price in Session persistiert + Fallback-Estimator",
      color: C.green
    },
    {
      problem: "Session-State geht verloren",
      solution: "ChromaDB-Persistenz mit TTL + alle kritischen Felder gespeichert",
      color: C.primary
    },
  ];

  challenges.forEach((c, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const cx = 0.5 + col * 4.7;
    const cy = 1.15 + row * 1.4;

    addCard(slide, cx, cy, 4.3, 1.2, C.card);
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: 0.08, h: 1.2, fill: { color: c.color }
    });
    slide.addText("❌ " + c.problem, {
      x: cx + 0.2, y: cy + 0.05, w: 3.9, h: 0.4,
      fontSize: 11, color: c.color, fontFace: "Calibri", bold: true, margin: 0
    });
    slide.addText("✅ " + c.solution, {
      x: cx + 0.2, y: cy + 0.5, w: 3.9, h: 0.55,
      fontSize: 10, color: C.text, fontFace: "Calibri", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 22: ARCHITEKTUR-ENTSCHEIDUNGEN
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "9", "Architektur-Entscheidungen");
  addFooter(slide, 22, TOTAL);

  const decisions = [
    { decision: "State Machine statt Agent-Chain", why: "Deterministisches Routing → vorhersagbar, günstig, debugbar", icon: "🔄" },
    { decision: "ChromaDB für Sessions + RAG", why: "Eine Datenbank für beides → kein Extra-Infrastruktur nötig", icon: "🗄️" },
    { decision: "Combined Classify+Extract", why: "1 LLM-Call statt 2 → 50% API-Kosten gespart", icon: "💰" },
    { decision: "Hot-Reload YAML-Prompts", why: "Admin ändert Prompts ohne Deploy → schnelle Iteration", icon: "🔥" },
    { decision: "Async HTTP + Sync Graph", why: "FastAPI I/O-async, Graph in Thread → kein Blocking", icon: "⚡" },
    { decision: "Provider-Fallback-Kette", why: "OpenAI → HuggingFace → Service bleibt online", icon: "🛡️" },
  ];

  decisions.forEach((d, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const dx = 0.5 + col * 4.7;
    const dy = 1.15 + row * 1.35;

    addCard(slide, dx, dy, 4.3, 1.15, C.card);
    slide.addText(d.icon, {
      x: dx + 0.15, y: dy + 0.1, w: 0.4, h: 0.4,
      fontSize: 18, align: "center", valign: "middle", margin: 0
    });
    slide.addText(d.decision, {
      x: dx + 0.6, y: dy + 0.1, w: 3.5, h: 0.35,
      fontSize: 12, color: C.dark, fontFace: "Georgia", bold: true, margin: 0
    });
    slide.addText(d.why, {
      x: dx + 0.6, y: dy + 0.5, w: 3.5, h: 0.55,
      fontSize: 10, color: C.muted, fontFace: "Calibri", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 23: ZAHLEN & FAKTEN
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.dark };
  slide.addText("Kidstorte in Zahlen", {
    x: 0.5, y: 0.3, w: 9, h: 0.6,
    fontSize: 28, color: C.textLight, fontFace: "Georgia", bold: true, margin: 0
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 0.95, w: 3, h: 0.04, fill: { color: C.primary }
  });
  addFooter(slide, 23, TOTAL);

  const stats = [
    { num: "14", label: "Nodes im\nState Machine", color: C.primary },
    { num: "20+", label: "API\nEndpoints", color: C.blue },
    { num: "10", label: "Pflichtfelder\npro Bestellung", color: C.green },
    { num: "3000+", label: "Zeilen\nPython Code", color: C.orange },
    { num: "6", label: "Prompt-\nTemplates", color: C.purple },
    { num: "60+", label: "Referenz-\nbilder Portfolio", color: C.sage },
  ];

  stats.forEach((s, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const sx = 0.8 + col * 3.1;
    const sy = 1.5 + row * 2.0;

    slide.addShape(pres.shapes.RECTANGLE, {
      x: sx, y: sy, w: 2.6, h: 1.6,
      fill: { color: s.color }, shadow: makeShadow(),
      transparency: 15
    });
    slide.addText(s.num, {
      x: sx, y: sy + 0.1, w: 2.6, h: 0.9,
      fontSize: 44, color: C.textLight, fontFace: "Georgia", bold: true,
      align: "center", valign: "middle", margin: 0
    });
    slide.addText(s.label, {
      x: sx, y: sy + 1.0, w: 2.6, h: 0.5,
      fontSize: 11, color: C.textLight, fontFace: "Calibri",
      align: "center", valign: "top", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 24: KEY LEARNINGS
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.light };
  addSectionHeader(slide, "✨", "Key Learnings");
  addFooter(slide, 24, TOTAL);

  const learnings = [
    { text: "Prompt Engineering ist iterativ — 80% der Bugs sind Prompt-Bugs, nicht Code-Bugs", color: C.primary },
    { text: "State Machines > Chain-of-Thought für produktionsreife Chatbots — deterministisch & debugbar", color: C.blue },
    { text: "RAG eliminiert Halluzination bei Preisen und Produktwissen — Fakten statt Fantasie", color: C.green },
    { text: "Session-Persistenz ist kritisch — jedes Feld das nicht gespeichert wird, geht verloren", color: C.orange },
    { text: "Graceful Degradation — jeder Service muss ohne den anderen funktionieren können", color: C.purple },
    { text: "LLM-Output ist nie deterministisch — immer Guards und Fallbacks einbauen!", color: C.red },
  ];

  learnings.forEach((l, i) => {
    const yy = 1.2 + i * 0.68;
    addCard(slide, 0.5, yy, 9.0, 0.55, C.card);
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y: yy, w: 0.08, h: 0.55, fill: { color: l.color }
    });
    slide.addShape(pres.shapes.OVAL, {
      x: 0.75, y: yy + 0.12, w: 0.3, h: 0.3,
      fill: { color: l.color }
    });
    slide.addText(String(i + 1), {
      x: 0.75, y: yy + 0.12, w: 0.3, h: 0.3,
      fontSize: 10, color: C.textLight, fontFace: "Calibri", bold: true,
      align: "center", valign: "middle", margin: 0
    });
    slide.addText(l.text, {
      x: 1.2, y: yy, w: 8.1, h: 0.55,
      fontSize: 12, color: C.text, fontFace: "Calibri",
      valign: "middle", margin: 0
    });
  });
})();

// ============================================================
// SLIDE 25: Q&A / END
// ============================================================
(() => {
  const slide = pres.addSlide();
  slide.background = { color: C.dark };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.06,
    fill: { color: C.primary }
  });

  slide.addText("Vielen Dank!", {
    x: 0, y: 1.0, w: 10, h: 1.0,
    fontSize: 48, color: C.textLight, fontFace: "Georgia", bold: true,
    align: "center", margin: 0
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 3.5, y: 2.1, w: 3, h: 0.04, fill: { color: C.primary }
  });

  slide.addText("Fragen & Diskussion", {
    x: 0, y: 2.4, w: 10, h: 0.6,
    fontSize: 22, color: C.accent, fontFace: "Calibri",
    align: "center", margin: 0
  });

  // Contact info
  slide.addText("🎂", {
    x: 4.5, y: 3.2, w: 1, h: 0.8,
    fontSize: 40, align: "center", valign: "middle", margin: 0
  });

  slide.addText([
    { text: "Schamja Shahag", options: { bold: true, breakLine: true, fontSize: 16 } },
    { text: "Masterschool — Software Engineering", options: { breakLine: true, fontSize: 12 } },
    { text: "", options: { breakLine: true } },
    { text: "Tech: Python · FastAPI · OpenAI · ChromaDB · LangSmith", options: { fontSize: 11 } },
  ], {
    x: 0, y: 4.0, w: 10, h: 1.2,
    color: C.textLight, fontFace: "Calibri",
    align: "center", valign: "top", margin: 0
  });
})();

// ============================================================
// SAVE
// ============================================================
const outputPath = "/Users/schamjashahag/Kidstorte-longchain/Kidstorte_Praesentation.pptx";
pres.writeFile({ fileName: outputPath }).then(() => {
  console.log("Presentation saved to: " + outputPath);
}).catch(err => {
  console.error("Error:", err);
});
