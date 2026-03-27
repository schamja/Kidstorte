"""
Erstellt die Kidstorte Projektbeschreibung als PDF.
Ausführen: python generate_pdf.py
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import PageBreak

# ── Farben ────────────────────────────────────────────────
BRAUN       = colors.HexColor("#5a3825")
BRAUN_HELL  = colors.HexColor("#c4956a")
BRAUN_BG    = colors.HexColor("#fdf6ee")
BLAU        = colors.HexColor("#2d6a9f")
DUNKEL      = colors.HexColor("#1a1a2e")
GRAU        = colors.HexColor("#555555")
HELLGRAU    = colors.HexColor("#f8f9fb")
GRAU_RAND   = colors.HexColor("#dde3ed")
WEISS       = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 2.2 * cm

# ── Stile ─────────────────────────────────────────────────
styles = getSampleStyleSheet()

def style(name, **kw):
    s = styles[name].clone(name + str(id(kw)))
    for k, v in kw.items():
        setattr(s, k, v)
    return s

S_TITLE = style("Title",
    fontName="Helvetica-Bold", fontSize=22,
    textColor=BRAUN, leading=26, spaceAfter=4)

S_SUBTITLE = style("Normal",
    fontName="Helvetica", fontSize=10,
    textColor=BRAUN_HELL, spaceAfter=2)

S_H2 = style("Heading2",
    fontName="Helvetica-Bold", fontSize=13,
    textColor=BRAUN, spaceBefore=18, spaceAfter=6)

S_H3 = style("Heading3",
    fontName="Helvetica-Bold", fontSize=10.5,
    textColor=DUNKEL, spaceBefore=10, spaceAfter=4)

S_BODY = style("Normal",
    fontName="Helvetica", fontSize=9.5,
    textColor=GRAU, leading=14, spaceAfter=5,
    alignment=TA_JUSTIFY)

S_GOAL = style("Normal",
    fontName="Helvetica", fontSize=10.5,
    textColor=BRAUN, leading=16, spaceAfter=6,
    alignment=TA_JUSTIFY)

S_CODE = style("Code",
    fontName="Courier-Bold", fontSize=9,
    textColor=BLAU)

S_BOLD = style("Normal",
    fontName="Helvetica-Bold", fontSize=9.5,
    textColor=DUNKEL)

S_CELL = style("Normal",
    fontName="Helvetica", fontSize=9,
    textColor=GRAU, leading=13)

S_CELL_BOLD = style("Normal",
    fontName="Helvetica-Bold", fontSize=9,
    textColor=BRAUN)

S_CELL_CODE = style("Normal",
    fontName="Courier-Bold", fontSize=8.5,
    textColor=BLAU)

S_SUMMARY = style("Normal",
    fontName="Helvetica", fontSize=10,
    textColor=colors.HexColor("#e8e0d8"),
    leading=16, alignment=TA_JUSTIFY)

S_FOOTER = style("Normal",
    fontName="Helvetica", fontSize=8,
    textColor=colors.HexColor("#aaaaaa"),
    alignment=TA_CENTER)

COL_W = PAGE_W - 2 * MARGIN

# ── Hilfsfunktionen ───────────────────────────────────────
def hr(color=BRAUN_HELL, thickness=1):
    return HRFlowable(width="100%", thickness=thickness,
                      color=color, spaceAfter=4, spaceBefore=2)

def p(text, sty=S_BODY):
    return Paragraph(text, sty)

def sp(h=6):
    return Spacer(1, h)

def section_title(text):
    return KeepTogether([p(text, S_H2), hr(BRAUN_HELL, 0.8)])

def table_header_row(cols):
    return [p(c, style("Normal", fontName="Helvetica-Bold",
                       fontSize=9, textColor=WEISS)) for c in cols]


def make_table(data, col_widths, header=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAUN),
        ("TEXTCOLOR", (0, 0), (-1, 0), WEISS),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WEISS, colors.HexColor("#fdf8f3")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e0d8d0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]
    t.setStyle(TableStyle(cmds))
    return t


# ── Dokument ──────────────────────────────────────────────
doc = SimpleDocTemplate(
    "Kidstorte_Projektbeschreibung.pdf",
    pagesize=A4,
    leftMargin=MARGIN, rightMargin=MARGIN,
    topMargin=MARGIN, bottomMargin=MARGIN,
    title="Kidstorte – Projektbeschreibung",
    author="Kidstorte Team",
)

story = []

# ── HEADER ────────────────────────────────────────────────
header_data = [[
    p("🎂  Kidstorte", S_TITLE),
    p("Projektbeschreibung · März 2026", style("Normal",
        fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#aaaaaa"),
        alignment=2))  # right
]]
header_t = Table(header_data, colWidths=[COL_W * 0.7, COL_W * 0.3])
header_t.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
]))
story.append(header_t)
story.append(p("KI-gestützter Bestell-Chatbot für Konditoreien", S_SUBTITLE))
story.append(hr(BRAUN, 2))
story.append(sp(8))

# ── 1. PROJEKTZIEL ────────────────────────────────────────
story.append(section_title("1.  Projektziel"))

goal_box_data = [[
    p("🎯  Kidstorte ist ein KI-gesteuerter Chatbot für eine Konditorei. "
      "Kunden beschreiben ihre <b>Traumtorte per Chat</b>, erhalten ein "
      "KI-generiertes Bild und geben am Ende eine Bestellung mit Kontaktdaten ab — "
      "vollständig automatisiert, ohne menschlichen Eingriff.", S_GOAL)
]]
goal_box = Table(goal_box_data, colWidths=[COL_W])
goal_box.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), BRAUN_BG),
    ("LEFTPADDING", (0, 0), (-1, -1), 14),
    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ("TOPPADDING", (0, 0), (-1, -1), 10),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ("LINEBEFORE", (0, 0), (0, -1), 4, BRAUN_HELL),
    ("ROUNDEDCORNERS", [0, 6, 6, 0]),
]))
story.append(goal_box)
story.append(sp(8))

story.append(p(
    "Der Bot stellt gezielte Fragen (Anlass, Geschmack, Gäste, Dekoration), "
    "versteht die Antworten mithilfe von KI, erstellt ein Tortenbild mit DALL-E "
    "und schickt die fertige Bestellung per E-Mail an Designer und Kunden. "
    "Im Admin-Panel kann der Betreiber alle Bestellungen verwalten und Bot-Texte live anpassen.",
    S_BODY))
story.append(sp(6))

# ── 2. GESPRÄCHSABLAUF ────────────────────────────────────
story.append(section_title("2.  Gesprächsablauf"))

flow_steps = [
    "👤 Kunde\nöffnet Website",
    "💬 Chat\nbeginn",
    "🤖 Bot stellt\nFragen",
    "🎂 Alle Infos\ngesammelt",
    "🖼️ KI-Bild\nerstellt",
    "📋 Adress-\nformular",
    "📧 E-Mails\ngesendet",
    "✅ Bestellung\ngespeichert",
]
cell_w = COL_W / len(flow_steps)
flow_data = [[
    p(s, style("Normal", fontName="Helvetica-Bold", fontSize=7.5,
               textColor=DUNKEL, alignment=TA_CENTER, leading=10))
    for s in flow_steps
]]
flow_t = Table(flow_data, colWidths=[cell_w] * len(flow_steps))
flow_t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), HELLGRAU),
    ("BOX", (0, 0), (-1, -1), 0.5, GRAU_RAND),
    ("INNERGRID", (0, 0), (-1, -1), 0.5, GRAU_RAND),
    ("TOPPADDING", (0, 0), (-1, -1), 7),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("ROUNDEDCORNERS", [6, 6, 6, 6]),
]))
story.append(flow_t)
story.append(sp(10))

# ── 3. PROJEKTSTRUKTUR ────────────────────────────────────
story.append(section_title("3.  Projektstruktur – Jede Datei erklärt"))
story.append(p("<b>Backend (Python / Server)</b>", S_H3))

backend_files = [
    ("main.py", "Der Kellner",
     "Empfängt alle Anfragen vom Browser, leitet sie weiter. "
     "Enthält alle API-Endpunkte: /api/chat, /api/submit-order, /admin."),
    ("graph.py", "Der Dirigent",
     "Steuert den Gesprächsablauf mit LangGraph. Entscheidet: "
     "Welcher Schritt kommt als nächstes?"),
    ("nodes.py", "Die Arbeiter",
     "Führt KI-Arbeit aus: Intent klassifizieren, Bestelldaten sammeln, "
     "Bild mit DALL-E generieren, Bestellung finalisieren."),
    ("state.py", "Das Gedächtnis",
     "Definiert den AgentState: intent, order_info, messages, "
     "image_url, order_complete, show_address_form …"),
    ("session_manager.py", "Der Aktenschrank",
     "Speichert jede Sitzung getrennt in ChromaDB. "
     "Ermöglicht Multi-User: Jeder Kunde hat seinen eigenen Chat."),
    ("order_db.py", "Das Bestellbuch",
     "Speichert abgeschlossene Bestellungen dauerhaft in SQLite. "
     "Funktionen: save_order(), get_all_orders(), update_order_status()."),
    ("email_service.py", "Der Briefträger",
     "Sendet HTML-E-Mails via SMTP an Designer (neue Bestellung) "
     "und Kunden (Bestätigung). Fällt sicher aus wenn SMTP fehlt."),
    ("config.py", "Die Einstellungen",
     "Lädt API-Keys und Passwörter aus .env. "
     "Stellt Lade/Speicher-Funktionen für YAML-Config bereit."),
    ("monitoring.py", "Die Statistiken",
     "Zählt Anfragen, Fehler und Antwortzeiten im Hintergrund. "
     "Erreichbar unter /metrics."),
]

backend_data = [table_header_row(["Datei", "Rolle", "Beschreibung"])]
for fname, role, desc in backend_files:
    backend_data.append([
        p(fname, S_CELL_CODE),
        p(role, S_CELL_BOLD),
        p(desc, S_CELL),
    ])
story.append(make_table(backend_data, [COL_W * 0.22, COL_W * 0.20, COL_W * 0.58]))
story.append(sp(10))

story.append(p("<b>Frontend (Browser / HTML)</b>", S_H3))
frontend_files = [
    ("templates/index.html", "Die Kunden-Website",
     "Chatfenster für Kunden. Zeigt Nachrichten, KI-Tortenbild "
     "und Adressformular bei Bestellabschluss."),
    ("templates/admin.html", "Das Admin-Panel",
     "Passwortgeschütztes Dashboard: Bestellungen verwalten, "
     "Bot-Texte live bearbeiten, Sitzungen anzeigen."),
    ("static/script.js", "Logik im Browser",
     "Sendet Nachrichten per Fetch-API, zeigt Antworten an, "
     "steuert Adressformular und Reset-Button."),
    ("static/style.css", "Das Design",
     "Alle visuellen Stile: Chat-Blasen, Adressformular, "
     "Admin-Tabellen, Animationen."),
]
frontend_data = [table_header_row(["Datei", "Rolle", "Beschreibung"])]
for fname, role, desc in frontend_files:
    frontend_data.append([
        p(fname, S_CELL_CODE),
        p(role, S_CELL_BOLD),
        p(desc, S_CELL),
    ])
story.append(make_table(frontend_data, [COL_W * 0.28, COL_W * 0.20, COL_W * 0.52]))
story.append(sp(10))

story.append(p("<b>Konfiguration</b>", S_H3))
config_files = [
    ("prompts_config.yaml",
     "Alle Bot-Texte und System-Prompts. Im Admin-Panel live änderbar, "
     "ohne Server-Neustart."),
    (".env",
     "Geheime Schlüssel: OpenAI API-Key, SMTP-Zugangsdaten, Admin-Passwort. "
     "Wird nie ins Git eingecheckt."),
    ("kidstorte.db",
     "SQLite-Datenbankdatei mit allen abgeschlossenen Bestellungen "
     "(automatisch erstellt)."),
    ("er-diagramm.html",
     "Interaktives ER-Diagramm der Datenbankstruktur (7 Entitäten, "
     "6 Relationen). Erreichbar unter /database-diagram."),
]
config_data = [table_header_row(["Datei", "Inhalt"])]
for fname, desc in config_files:
    config_data.append([p(fname, S_CELL_CODE), p(desc, S_CELL)])
story.append(make_table(config_data, [COL_W * 0.30, COL_W * 0.70]))
story.append(sp(10))

# ── 4. TECHNOLOGIEN ───────────────────────────────────────
story.append(section_title("4.  Verwendete Technologien"))

tech = [
    ("⚡ FastAPI", "Python Web-Framework. Verarbeitet HTTP-Anfragen schnell und asynchron."),
    ("🔗 LangGraph", "Steuert den Gesprächsablauf als Graph. Jeder Knoten ist ein Schritt im Chat."),
    ("🧠 GPT-4.1-mini", "Beantwortet Kundenfragen, klassifiziert Absichten, sammelt Bestelldaten."),
    ("🖼️ DALL-E 3", "Generiert ein realistisches Bild der bestellten Torte aus der Beschreibung."),
    ("🗄️ ChromaDB", "Vektordatenbank für Sitzungen (Multi-User) und RAG-Wissensabruf."),
    ("💾 SQLite", "Relationale Datenbank für dauerhafte Bestellspeicherung mit Kundendaten."),
    ("📧 SMTP / GMX", "Automatischer E-Mail-Versand an Designer und Kunden nach Bestellabschluss."),
    ("🐍 Python + Pydantic", "Gesamte Serverlogik in Python. Pydantic validiert alle Datenstrukturen."),
]

tech_data = []
row = []
for i, (name, desc) in enumerate(tech):
    cell_content = [
        p(name, style("Normal", fontName="Helvetica-Bold",
                      fontSize=9.5, textColor=DUNKEL, spaceBefore=0)),
        p(desc, style("Normal", fontName="Helvetica",
                      fontSize=8.5, textColor=GRAU, leading=12)),
    ]
    row.append(cell_content)
    if len(row) == 2:
        tech_data.append(row)
        row = []
if row:
    row.append([""])
    tech_data.append(row)

tech_t = Table(tech_data, colWidths=[COL_W / 2 - 4, COL_W / 2 - 4],
               hAlign="LEFT", spaceBefore=4)
tech_t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), HELLGRAU),
    ("BOX", (0, 0), (-1, -1), 0, GRAU_RAND),
    ("INNERGRID", (0, 0), (-1, -1), 4, WEISS),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("ROUNDEDCORNERS", [6, 6, 6, 6]),
]))
story.append(tech_t)
story.append(sp(10))

# ── 5. KI-KONZEPTE ────────────────────────────────────────
story.append(section_title("5.  Eingesetzte KI-Konzepte"))

concepts = [
    ("LangGraph", "Stateful Agent als Graph:",
     "Der Gesprächsfluss wird als gerichteter Graph modelliert. "
     "Jeder Knoten ist eine Funktion (z.B. collect_order_info). "
     "Der Graph entscheidet anhand des Zustands, welcher Knoten als nächstes läuft."),
    ("RAG", "Retrieval Augmented Generation:",
     "Der Bot greift auf Wissen aus gespeicherten Dokumenten (z.B. Tortenkatalog) zu, "
     "das in ChromaDB als Vektoren gespeichert ist, und fließt in seine Antworten ein."),
    ("Intent", "Intent-Klassifikation:",
     "Bei jeder Nachricht erkennt der Bot die Absicht des Kunden "
     "(bestellen / fragen / Bild wünschen / bestätigen / abbrechen) "
     "und wählt die passende Aktion."),
    ("Multi-User", "Session-Management:",
     "Jeder Kunde bekommt eine eindeutige Session-ID per Cookie. "
     "Der Agent-Zustand wird pro Sitzung in ChromaDB gespeichert, "
     "sodass viele Kunden gleichzeitig chatten können."),
    ("DALL-E", "Text-to-Image:",
     "Aus den gesammelten Tortenmerkmalen wird ein beschreibender Prompt gebaut "
     "und an DALL-E 3 gesendet — das Ergebnis ist ein realistisches Tortenbild."),
    ("Hot-Reload", "Live-Konfiguration:",
     "System-Prompts werden aus einer YAML-Datei geladen und bei jedem Request "
     "neu eingelesen. Änderungen wirken sofort ohne Server-Neustart."),
]

concept_data = []
for tag, bold, desc in concepts:
    concept_data.append([
        p(tag, style("Normal", fontName="Helvetica-Bold", fontSize=8,
                     textColor=WEISS, alignment=TA_CENTER)),
        [p(f"<b>{bold}</b> {desc}", S_CELL)],
    ])

concept_t = Table(concept_data, colWidths=[COL_W * 0.14, COL_W * 0.86])
concept_t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (0, -1), BRAUN),
    ("BACKGROUND", (1, 0), (1, -1), WEISS),
    ("ROWBACKGROUNDS", (1, 0), (1, -1), [WEISS, colors.HexColor("#fdf8f3")]),
    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e0d8d0")),
    ("TOPPADDING", (0, 0), (-1, -1), 7),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TEXTCOLOR", (0, 0), (0, -1), WEISS),
    ("ROUNDEDCORNERS", [4, 4, 4, 4]),
]))
story.append(concept_t)
story.append(sp(10))

# ── 6. ZUSAMMENFASSUNG ────────────────────────────────────
story.append(section_title("6.  Zusammenfassung für den Mentor"))

summary_bg_data = [[
    p(
        "\"<b>Kidstorte</b> ist ein vollständiger KI-Chatbot für eine Konditorei, entwickelt mit "
        "<b>FastAPI</b> (Web-Server), <b>LangGraph</b> (Gesprächssteuerung) und "
        "<b>OpenAI GPT + DALL-E</b> (KI und Bildgenerierung).<br/><br/>"
        "Kunden beschreiben ihre Traumtorte im Chat. Der Bot sammelt alle nötigen Informationen, "
        "erstellt ein <b>KI-generiertes Bild</b> der Torte und nimmt die Bestellung mit Kontaktdaten entgegen. "
        "Die Bestellung wird in <b>SQLite</b> gespeichert und per <b>E-Mail</b> an Designer und Kunden gesendet.<br/><br/>"
        "Das Projekt demonstriert: <b>LangGraph Agents, RAG, Multi-User Sessions, REST-API Design, "
        "Datenbankintegration und KI-Bildgenerierung</b> — alles in einem produktionsreifen System.\"",
        S_SUMMARY
    )
]]
summary_box = Table(summary_bg_data, colWidths=[COL_W])
summary_box.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), DUNKEL),
    ("LEFTPADDING", (0, 0), (-1, -1), 20),
    ("RIGHTPADDING", (0, 0), (-1, -1), 20),
    ("TOPPADDING", (0, 0), (-1, -1), 16),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
    ("ROUNDEDCORNERS", [8, 8, 8, 8]),
]))
story.append(summary_box)
story.append(sp(16))

# ── FOOTER ────────────────────────────────────────────────
story.append(hr(BRAUN_HELL, 0.5))
story.append(sp(4))
story.append(p(
    "🎂  Kidstorte – KI-Chatbot Projekt  ·  "
    "FastAPI · LangGraph · OpenAI · ChromaDB · SQLite  ·  März 2026",
    S_FOOTER
))

# ── PDF BAUEN ─────────────────────────────────────────────
doc.build(story)
print("✅ PDF erstellt: Kidstorte_Projektbeschreibung.pdf")
