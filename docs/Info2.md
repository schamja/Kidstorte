# 🎂 Kidstorte – KI-gestützter Kuchenbestellungs-Agent

Eine vollständige FastAPI-Webanwendung mit einem LangGraph-basierten KI-Agenten, der Kunden durch den Bestellprozess für individuelle Torten führt.

---

## 📁 Projektstruktur & Datei-Übersicht

```
kidstorte/
├── main.py               # FastAPI-Server, alle HTTP-Endpunkte
├── graph.py              # Agent-Ablauflogik (Routing zwischen Nodes)
├── nodes.py              # Einzelne KI-Aktionsschritte (Node-Funktionen)
├── state.py              # Zentrales Datenobjekt (AgentState / Klemmbrett)
├── session_manager.py    # Session-Persistenz via ChromaDB
├── order_db.py           # SQLite-Datenbank für abgeschlossene Bestellungen
├── config.py             # Konfiguration, Umgebungsvariablen, YAML-Loader
├── prompts_config.yaml   # KI-Prompts, Pflichtfelder, Fragen (hot-reloadable)
├── monitoring.py         # Logging (JSON) + In-Memory Metriken
├── error_handler.py      # Fehlerbehandlung, Retry-Decorator, safe_node
├── cost_optimizer.py     # Token-Schätzung, Response-Cache, Modell-Routing
├── email_service.py      # SMTP-E-Mail-Versand (Bestätigung + Bewertung)
├── pdf_order.py          # PDF-Generierung mit ReportLab
├── generate_pdf.py       # (Hilfsscript für PDF-Generierung)
├── kidstorte.db          # SQLite-Datenbankdatei
├── er-diagramm.html      # ER-Diagramm der Datenbankstruktur
├── templates/            # Jinja2 HTML-Templates (index, admin, bewertung)
├── static/               # Statische Dateien (Bilder, PDFs)
│   ├── images/           # KI-generierte Kuchenvorschaubilder
│   └── pdfs/             # Gespeicherte Bestell-PDFs
├── documents/            # Wissensbasis für RAG (Preislisten, FAQ etc.)
└── chroma_db/            # ChromaDB-Datenbankordner (Sessions + Embeddings)
```

---

## 🏗️ Architektur-Überblick

Das System besteht aus **vier Schichten**, die sauber voneinander getrennt sind:

```
┌─────────────────────────────────────────┐
│              BROWSER / CLIENT           │
│         (index.html, Admin-Panel)       │
└──────────────────┬──────────────────────┘
                   │  HTTP / JSON
┌──────────────────▼──────────────────────┐
│              main.py                    │
│         FastAPI Web-Server              │
│  (Endpunkte, Session-Cookie, Routing)   │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│    graph.py  +  nodes.py                │
│         KI-Agent (LangGraph-Muster)     │
│  (Intent → Extract → Ask/Answer/Image)  │
└──────────┬──────────────┬───────────────┘
           │              │
┌──────────▼──┐    ┌──────▼──────────────┐
│session_mgr  │    │     order_db.py      │
│(ChromaDB)   │    │     (SQLite)         │
│Chat-Verlauf │    │  Abgeschl. Bestellg. │
└─────────────┘    └─────────────────────┘
```

---

## 🔄 Wie die Dateien zusammenhängen

### 1. `state.py` – Das Klemmbrett aller Dateien

`state.py` definiert `AgentState` – ein TypedDict-Objekt, das **alle Informationen** enthält, die zwischen den 
Verarbeitungsschritten geteilt werden. Es ist das Herzstück, das alle anderen Dateien verbindet.

```
AgentState enthält:
  session_id        → Wer schreibt gerade?
  user_input        → Was hat der Kunde gesagt?
  messages          → Der gesamte Gesprächsverlauf
  intent            → Was will der Kunde? (greeting/order/price/...)
  order_info        → Gesammelte Bestelldetails (Anlass, Gäste, Geschmack, ...)
  missing_fields    → Was fehlt noch?
  order_complete    → Ist die Bestellung vollständig?
  question_todo     → TODO-Liste: welche Felder wurden schon gefragt?
  response          → Die Antwort, die der Kunde bekommt
  image_url         → Link zum generierten Kuchenbild

  
```

**Datenfluss:** `main.py` lädt den State → gibt ihn an `graph.py` → `graph.py` reicht ihn durch alle 
`nodes.py`-Funktionen → `main.py` speichert den aktualisierten State.

---

### 2. `config.py` + `prompts_config.yaml` – Konfigurationszentrale

`config.py` liest alle Umgebungsvariablen (API-Keys, SMTP, Passwörter) aus der `.env`-Datei und stellt sie dem Rest 
des Projekts zur Verfügung. Es lädt außerdem die `prompts_config.yaml`.

`prompts_config.yaml` enthält:
- **KI-Prompts** für jeden Schritt (Intent-Klassifikation, Extraktion, Preisberechnung, ...)
- **Pflichtfelder** der Bestellung (`anlass`, `gaeste`, `geschmack`, ...)
- **Fragen** für jedes Pflichtfeld
- **Bot-Persönlichkeit** (Ton, Sprache)
- **max_orders_per_day** (Kapazitätslimit)

**Hot-Reload:** `config.py` prüft beim Laden die `mtime` der YAML-Datei. Wenn ein Admin im Panel einen Prompt ändert, 
wird die neue Version sofort geladen – ohne Server-Neustart.

```
config.py ◄──── .env (geheime Keys)
    │
    └──► prompts_config.yaml ◄──► Admin-Panel (main.py /admin/prompts)
```

---

### 3. `graph.py` – Der Dirigent

`graph.py` enthält die `CakeDreamsGraph`-Klasse mit der zentralen `run()`-Methode. Sie empfängt den `AgentState` 
und die Nutzernachricht, und entscheidet welche `nodes.py`-Funktionen in welcher Reihenfolge aufgerufen werden.
Das "Gehirn" & Logik
    .graph.py: Definiert den Workflow. Agiert als Regisseur, der den State zwischen den einzelnen Schritten (Nodes) routet.
    .nodes.py: Enthält die funktionalen Einheiten (Klassifizierung, Extraktion, Preisberechnung, 
    Bildgenerierung).
    .state.py: Das zentrale AgentState-Objekt fungiert als "Single Source of Truth" für den aktuellen 
    Gesprächs- und Bestellstatus.

```
graph.run(state, user_input):
  
  Schritt 0: guardrail()         → Schädliche Eingaben blockieren
  Schritt 1: classify_and_extract() → Intent erkennen + Bestellinfos extrahieren
  Schritt 2: Routing nach Intent:
  
    "greeting"  → greet()
    "order"     → extract_info() → check_complete()
                    → summarize_order() ODER ask_next()
    "price"     → retrieve_docs() → calculate_price()
    "image"     → generate_image()
    "info"      → retrieve_docs() → answer_question()
    "change"    → update_order()
    "finalize"  → finalize_order()
    "offtopic"  → redirect()
```

**Wichtig:** `graph.py` ist **stateless** – es speichert selbst keine Daten. Das Session-Management übernimmt 
der `SessionManager`.

---

### 4. `nodes.py` – Die einzelnen KI-Aktionen

Jede Funktion in `nodes.py` ist ein Schritt im Agenten-Ablauf. Sie empfangen den `AgentState`, führen eine Aktion aus 
(meistens ein OpenAI-API-Call), und geben den aktualisierten State zurück.

| Node-Funktion            | Was sie tut |

| `guardrail()`            | Prüft ob die Eingabe schädlich/unangemessen ist |
| `classify_and_extract()` | **Kombinierter LLM-Call:** Erkennt Intent UND extrahiert Bestellinfos in einem Schritt (kostenoptimiert) 
| `reet()`                 |Gibt Willkommens-Nachricht aus |
| `extract_info()`         | Extrahiert Bestelldetails aus dem Gespräch (JSON-Output) |
| `check_complete()`       | Prüft ob alle Pflichtfelder gefüllt sind |
| `ask_next()`             | Stellt die nächste offene Frage (nutzt `question_todo`) |
| `summarize_order()`      | Zeigt vollständige Bestellzusammenfassung |
| `retrieve_docs()`        | Holt relevante Dokumente aus ChromaDB (RAG) |
| `calculate_price()`      | Berechnet Preis als HTML-Tabelle |
| `answer_question()`      | Beantwortet allgemeine Fragen (Info/FAQ) |
| `generate_image()`       | Generiert KI-Vorschaubild des Kuchens via DALL-E |
| `update_order()`         | Ändert bereits gemachte Bestellangaben |
| `redirect()`             | Leitet Offtopic-Nachrichten höflich zurück |
| `finalize_order()`       | Schließt Bestellung ab, zeigt Adressformular |

**Alle Nodes sind mit `@safe_node` (aus `error_handler.py`) dekoriert** – fängt Fehler ab und gibt nutzerfreundliche 
Fallback-Antworten.

---

### 5. `session_manager.py` – Das Gedächtnis

Der `SessionManager` speichert den kompletten `AgentState` für jede aktive Sitzung in **ChromaDB** (eine Vektor-Datenbank). 
So "erinnert" sich der Agent an frühere Nachrichten, auch wenn der Browser-Tab geschlossen wird.

```
Ablauf pro Chat-Nachricht:
  1. Browser sendet Cookie (session_id)
  2. session_mgr.load_session(id)  → State aus ChromaDB laden
  3. graph.run(state, user_input)  → State verarbeiten
  4. session_mgr.save_session(id, state) → State zurückspeichern
```

- Sessions laufen nach `SESSION_TTL_HOURS` (24h) ab
- `cleanup_old_sessions()` wird beim Server-Start automatisch aufgerufen

---

### 6. `order_db.py` – Die Bestelldatenbank

Während `session_manager.py` die aktiven Gespräche speichert, speichert `order_db.py` **abgeschlossene Bestellungen** 
dauerhaft in einer **SQLite-Datenbank** (`kidstorte.db`).
order_db.py ist das Kassenbuch des Ladens – jede abgeschlossene Bestellung, jede Bewertung, jeder Status-Wechsel wird 
hier dauerhaft aufgeschrieben.
**Datenbank-Schema:**

```
orders Tabelle:
  id, session_id, order_info (JSON), customer_name, customer_email,
  customer_phone, customer_street, customer_plz, customer_city,
  liefertermin, total_price, status, created_at

ratings Tabelle:
  id, order_id (→ orders), rating (1-5), comment, created_at
```

**Status-Workflow einer Bestellung:**
```
neu → in_bearbeitung → fertig → (Bewertungseinladung per E-Mail)
                     → storniert
```

---

### 7. `main.py` – Der Web-Server

`main.py` ist der **Einstiegspunkt** der Anwendung. Es verbindet alle Komponenten und stellt HTTP-Endpunkte bereit.

```
main.py importiert und nutzt:
  ├── graph.py         → graph.run(state, question)
  ├── session_manager  → load/save sessions
  ├── order_db.py      → save_order, get_all_orders, ...
  ├── config.py        → load_prompts_config
  ├── monitoring.py    → metrics.inc(), metrics.record_tokens()
  ├── cost_optimizer   → response_cache, estimate_tokens
  ├── email_service    → send_order_email, send_rating_invite
  └── pdf_order.py     → save_order_pdf
```

---

### 8. `monitoring.py` – Die Blackbox

`monitoring.py` hat zwei Aufgaben:

**Strukturiertes Logging** – Alle Log-Einträge werden als JSON ausgegeben, was maschinelles Auslesen (z.B. durch 
Log-Aggregation-Tools) erleichtert.

**In-Memory Metriken** – Die `Metrics`-Klasse zählt intern:
- Anzahl Chat-Requests, Fehler, Erfolge
- Latenz-Statistiken (Durchschnitt, P50, P95, P99)
- Token-Verbrauch und geschätzte API-Kosten

Abrufbar über `GET /metrics` (nur für Admins).

---

### 9. `error_handler.py` – Das Sicherheitsnetz

Drei Werkzeuge für robuste Fehlerbehandlung:

| Werkzeug | Zweck |

| `@retry_on_transient` | Wiederholt OpenAI-API-Calls bei Netzwerkfehlern (mit exponentiellem Backoff) |
| `parse_llm_json()` | Parst JSON aus LLM-Antworten; bei Fehler automatischer Retry mit Feedback ans Modell |
| `@safe_node` | Decorator für alle Node-Funktionen: fängt Ausnahmen ab, setzt Fallback-Antwort |

---

### 10. `cost_optimizer.py` – Kostenkontrolle

Drei Mechanismen um API-Kosten zu senken:

| Mechanismus            | Funktion |

| `get_model_for_task()` | Routet einfache Aufgaben (Klassifikation, Extraktion) zu `gpt-4o-mini`, komplexe zu `gpt-4o` |
| `ResponseCache`        | In-Memory Cache (SHA256-Hash) – gibt gecachte Antworten zurück, wenn derselbe Prompt erneut auftaucht |
| `truncate_messages()`  | Kürzt den Gesprächsverlauf auf max. 3000 Tokens, damit nicht das gesamte Gespräch mit jedem Request gesendet wird |

---

### 11. `email_service.py` – Benachrichtigungen

Versendet drei Arten von E-Mails via SMTP:

| Funktion                      | Wann?                 | An wen? |

| `send_order_email()`          | Nach Bestellabschluss | Designer & Kunde |
| `send_order_email_with_pdf()` | Nach Bestellabschluss (mit PDF-Anhang) | Designer & Kunde |
| `send_rating_invite()`        | Wenn Admin Status auf "fertig" setzt | Kunde |

Wenn SMTP nicht konfiguriert ist, wird der Versand übersprungen und nur geloggt – kein Absturz.

---

### 12. `pdf_order.py` – Bestellbestätigung als PDF

Generiert mit **ReportLab** professionelle PDF-Bestätigungen.

Das PDF enthält:
- Header-Banner mit Kidstorte-Logo
- Bestellnummer & Datum
- Kundendaten
- Alle Bestelldetails (Anlass, Gäste, Geschmack, Dekoration, ...)
- Geschätzter Gesamtpreis (berechnet aus interner Preistabelle)
- KI-generiertes Vorschaubild des Kuchens (falls vorhanden)
- Kontaktinformationen

PDFs werden unter `static/pdfs/{order_id}.pdf` gespeichert und sind über `/api/order-pdf/{id}` abrufbar.




## 🔄 Vollständiger Ablauf einer Bestellung

```
1. KUNDE öffnet die Seite
   └─► Browser bekommt Session-Cookie (session_id)

2. KUNDE schreibt "Hallo"
   └─► POST /api/chat
       ├─ session_mgr.load_session() → leerer State
       ├─ graph.run(state, "Hallo")
       │   ├─ guardrail() → OK
       │   ├─ classify_and_extract() → intent="greeting"
       │   └─ greet() → "Hallo! Wie kann ich helfen?"
       └─ session_mgr.save_session()

3. KUNDE gibt Bestelldetails ein (mehrere Nachrichten)
   └─► POST /api/chat (je Nachricht)
       ├─ intent="order"
       ├─ extract_info() → füllt order_info
       ├─ check_complete() → fehlende Felder prüfen
       └─ ask_next() → stellt nächste Frage

4. BESTELLUNG KOMPLETT
   └─► summarize_order() → zeigt alle Details
       └─► finalize_order() → show_address_form=True

5. KUNDE füllt Adressformular aus
   └─► POST /api/submit-order
       ├─ order_db.save_order() → SQLite
       ├─ pdf_order.save_order_pdf() → PDF generieren
       ├─ email_service.send_order_email_with_pdf() → E-Mails senden
       └─ Antwort mit order_id + pdf_url

6. ADMIN setzt Status auf "fertig"
   └─► POST /admin/orders/{id}/status
       └─ email_service.send_rating_invite() → Bewertungseinladung

7. KUNDE bewertet
   └─► POST /bewertung/{id}
       └─ order_db.save_rating()
```

---

## 🚀 Installation & Setup

### Voraussetzungen

- Python 3.11+
- OpenAI API-Key

### 1. Abhängigkeiten installieren

```bash
pip install fastapi uvicorn openai chromadb reportlab pyyaml python-dotenv
```

### 2. `.env`-Datei erstellen

```env
OPENAI_API_KEY=sk-...
ADMIN_PASSWORD=mein-sicheres-passwort
CHAT_MODEL=gpt-4o-mini
IMAGE_MODEL=gpt-image-1

# Optional: E-Mail
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=meine@email.de
SMTP_PASSWORD=app-passwort
DESIGNER_EMAIL=designer@kidstorte.de
SHOP_NAME=Kidstorte
```

### 3. Server starten

```bash
uvicorn main:app --host 0.0.0.0 --port 5001 --reload
```

### 4. Anwendung öffnen

- **Chat-Interface:** `http://localhost:5001`
- **Admin-Panel:** `http://localhost:5001/admin/login`
- **Metriken:** `http://localhost:5001/metrics`
- **ER-Diagramm:** `http://localhost:5001/database-diagram`

---

## 🛠️ Admin-Panel Funktionen

| Bereich        | URL                      | Funktion |
| Dashboard      | `/admin`                 | Übersicht: Sessions, Bestellungen, Statistiken |
| Prompts        | `/admin/prompts` (POST)  | KI-Texte & Bot-Ton anpassen (Hot-Reload) |
| Bestellungen   | `/admin/orders`          | Alle Bestellungen einsehen, Status ändern |
| Bewertungen    | `/admin/ratings`         | Alle Kundenbewertungen + Durchschnitt |
| Kapazität      | `/admin/capacity` (POST) | Max. Bestellungen pro Tag konfigurieren |
| Sessions       | `/admin/sessions/cleanup`| Abgelaufene Sessions löschen |

---

## 🧩 Technologie-Stack

| Schicht               |Technologie |
| Web-Framework         |FastAPI + Uvicorn |
| KI / LLM              | OpenAI GPT-4o-mini / GPT-4o |
| Bildgenerierung       | OpenAI gpt-image-1 / DALL-E 3 |
| Agent-Logik           | Eigenes LangGraph-Muster (stateless nodes) |
| Session-Speicher      | ChromaDB (Vektordatenbank) |
| Bestelldatenbank      | SQLite via `sqlite3` |
| PDF-Generierung       | ReportLab |
| E-Mail                | Python `smtplib` + MIME |
| Templates             | Jinja2 |
| Konfiguration         | YAML + python-dotenv |
| Monitoring            | Eigene In-Memory Metriken + JSON-Logging |

---

## 📊 Datenbankstruktur

Das vollständige ER-Diagramm ist unter `/database-diagram` abrufbar.

```
orders (Haupttabelle)
  ├── id (PK)
  ├── session_id (→ ChromaDB Session)
  ├── order_info (JSON: alle Kuchendetails)
  ├── customer_* (Name, Email, Phone, Adresse)
  ├── liefertermin
  ├── total_price
  ├── status (neu/in_bearbeitung/fertig/storniert)
  └── created_at

ratings (Bewertungen)
  ├── id (PK)
  ├── order_id (FK → orders)
  ├── rating (1-5)
  ├── comment
  └── created_at
```

---

## 💡 Wichtige Design-Entscheidungen

**Stateless Graph:** Der Agent (`graph.py`, `nodes.py`) enthält selbst keine Daten. Der gesamte Zustand lebt im `AgentState`, 
der von außen (durch `session_manager.py`) verwaltet wird. Das macht den Agenten leicht testbar und skalierbar.

**Kombinierter LLM-Call:** `classify_and_extract()` erkennt den Intent UND extrahiert Bestellinfos in einem einzigen 
API-Call (statt zwei separaten Calls). Das spart ~50% der API-Kosten pro Nachricht.

**Hot-Reload für Prompts:** Die `prompts_config.yaml` wird mit `mtime`-Check gecacht. Änderungen im Admin-Panel sind 
sofort wirksam, ohne Server-Neustart.

**Zwei Datenbanken:** ChromaDB für aktive Sessions (kurzlebig, TTL 24h), SQLite für abgeschlossene Bestellungen (dauerhaft). 
Jede Datenbank ist optimal für ihren Anwendungsfall.

**Graceful Degradation:** E-Mail und PDF sind nicht kritisch. Schlägt der Versand fehl, wird die Bestellung trotzdem 
gespeichert und der Fehler geloggt – kein Absturz.

#######################################################################
📁 Wo werden welche Dateien gespeichert?

kidstorte/
│
├── chroma_db/          ← ChromaDB speichert hier
│   └── (automatisch generierte Dateien)
│
├── kidstorte.db        ← SQLite speichert hier (eine einzige Datei)
│
├── static/
│   ├── images/         ← KI-generierte Kuchenbilder (.png)
│   └── pdfs/           ← Bestellbestätigungen (1.pdf, 2.pdf, ...)
│
└── documents/          ← Wissensbasis für die KI (Preislisten, FAQ)

🗄️ Was macht ChromaDB – einfach erklärt
ChromaDB ist wie ein Aktenschrank mit zwei Schubladen:
Schublade 1 – Sessions (Gespräche)
sessions/
  ├── abc123...  → { messages: [...], order_info: {...} }  ← User A
  ├── def456...  → { messages: [...], order_info: {...} }  ← User B
  └── ghi789...  → { messages: [...], order_info: {...} }  ← User C
Jeder User hat seinen eigenen Eintrag. Nach 24 Stunden wird er automatisch gelöscht.
Schublade 2 – Wissensbasis (RAG)
cake_chunks/
  ├── chunk_1  → "Schokoladenkuchen kostet ab 35€..."
  ├── chunk_2  → "Lieferung kostet 5-15€ je nach Entfernung..."
  └── chunk_3  → "Zitronenkuchen ist glutenfrei..."
Das sind die Dokumente aus dem documents/ Ordner – zerstückelt und gespeichert, damit die KI gezielt darin suchen kann.

🆚 ChromaDB vs. SQLite – der Unterschied
ChromaDBSQLite (kidstorte.db)WasAktive GesprächeAbgeschlossene BestellungenWie lange24 Stunden (TTL)Für immerWann 
gespeichertBei jeder Chat-NachrichtNur wenn Kunde bestellt hatWer löschtAutomatisch nach 24hNur manuell (Admin)Beispiel-Inhalt"User schreibt gerade, hat Schoko gewählt...""Bestellung #42, Max Müller, 12.03.2026"

🔄 Der Ablauf ganz konkret
User schreibt "Hallo"
        │
        ▼
main.py liest Cookie → session_id = "abc123"
        │
        ▼
session_manager.py fragt ChromaDB:
  "Hast du was für abc123?"
        │
   ┌────┴────┐
  Ja        Nein
   │         │
   │         └─► neuer leerer State
   │
   └─► gespeicherter State laden
        │
        ▼
graph.py verarbeitet
        │
        ▼
session_manager.py speichert
aktualisierten State → ChromaDB

Kurz gesagt:

ChromaDB = Kurzzeitgedächtnis (solange das Gespräch läuft)
SQLite = Langzeitgedächtnis (die fertige Bestellung für immer)

################################

ingest.py ist der Bibliothekar – er liest alle Bücher, schreibt Stichwortkarten und sortiert alles ein.
retrieve_docs() ist der Suchende – er fragt den Bibliothekar und bekommt die passende Karte.


Was ingest.py macht – Schritt für Schritt
Es ist ein einmaliges Vorbereitungs-Script. Du führst es einmal aus, bevor der Server startet.

Der Ablauf konkret
documents/
  ├── preise.md
  ├── faq.md
  └── allergene.md
        │
        ▼
ingest.py liest jede .md Datei
        │
        ▼
chunk_by_sections() → zerstückelt bei "## Überschriften"
        │
        ▼
OpenAI Embedding → jeder Chunk wird zu Zahlen umgewandelt
        │
        ▼
ChromaDB speichert: Text + Zahlen + Quelle

Die eine wichtige Funktion erklärt
pythondef chunk_by_sections(text):
    chunks = []
    for section in text.split("\n## "):  # trennt bei jeder Überschrift
```

Aus einer langen Datei werden kleine Stücke:
```
preise.md (eine große Datei)
│
├── ## Schokoladenkuchen      → chunk_1
├── ## Vanillekuchen          → chunk_2  
├── ## Lieferkosten           → chunk_3
└── ## Allergene              → chunk_4
```

**Warum aufteilen?** Weil die KI gezielt nur den relevanten Chunk braucht – nicht die ganze Datei.

---

## Was ein Embedding ist

Das ist der wichtigste Teil den du verstehen solltest:
```
"Schokoladenkuchen kostet 35€"
            │
            ▼
OpenAI Embedding Model
            │
            ▼
[0.231, -0.847, 0.412, 0.093, ...]  ← 1536 Zahlen
```

Diese Zahlen beschreiben die **Bedeutung** des Textes. Ähnliche Bedeutung = ähnliche Zahlen.
```
"Was kostet Schoko?"     → [0.229, -0.851, 0.408, ...]
"Schokoladenkuchen 35€"  → [0.231, -0.847, 0.412, ...]
                                │
                         fast identisch! ✅
                         ChromaDB findet den richtigen Chunk

Der clevere Check – kein doppeltes Einlesen
pythonexisting = collection.get(ids=[chunk_id])
if existing and existing["ids"]:
    print(f"  Überspringe: {chunk_id}")  # schon drin → überspringen
    continue
```

Wenn du `ingest.py` ein zweites Mal ausführst, werden bereits gespeicherte Chunks **nicht nochmal** zu 
OpenAI geschickt. Spart Kosten.

---

## Zusammenspiel mit dem Rest
```
ingest.py                    nodes.py (retrieve_docs)
(einmalig vorher)            (bei jedem Chat)
      │                             │
      ▼                             ▼
ChromaDB: cake_chunks    ←→  ChromaDB: cake_chunks
  speichert Chunks              sucht passende Chunks
  + Embeddings                  für die Kundenfrage
```

**Konkret beim Chat:**
```
Kunde fragt: "Was kostet Lieferung?"
      │
      ▼
retrieve_docs() berechnet Embedding der Frage
      │
      ▼
ChromaDB vergleicht mit allen gespeicherten Embeddings
      │
      ▼
findet: chunk "Lieferkosten" aus faq.md → gibt Text zurück
      │
      ▼
KI antwortet mit diesem Text als Grundlage
