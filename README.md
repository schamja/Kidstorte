
# Kidstorte – KI-gestützter Bestellassistent

Ein KI-Kundenberater für eine Konditorei, gebaut nach dem **LangGraph-Pattern**:
Nodes + Edges + Shared State.

## Architektur

```
┌──────────────────────────────────────────────────────────┐
│                      SHARED STATE                         │
│  user_input, messages, intent, order_info, context, ...  │
└──────────────────────────┬───────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │  CLASSIFY   │  ← Node 1: Intent erkennen
                    │  INTENT     │
                    └──────┬──────┘
                           │
          ┌────────┬───────┼────────┬─────────┬──────────┐
          ▼        ▼       ▼        ▼         ▼          ▼
       GREET    ORDER    PRICE    IMAGE      INFO     OFFTOPIC
         │        │        │        │         │          │
         │    EXTRACT   RETRIEVE  GENERATE  RETRIEVE   REDIRECT
         │    INFO      DOCS     IMAGE     DOCS         │
         │        │        │                  │          │
         │    CHECK     CALC               ANSWER       │
         │    COMPLETE  PRICE              QUESTION      │
         │        │                                      │
         │   ┌────┴────┐                                 │
         │   ▼         ▼                                 │
         │  ASK      SUMMARIZE                           │
         │  NEXT     ORDER                               │
         │                                               │
         └───────────────────┬───────────────────────────┘
                             ▼
                          RESPONSE
```

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `app/state.py` | **Shared State** – Das zentrale Datenobjekt (OrderInfo, AgentState) |
| `app/nodes.py` | **Nodes** – 14 eigenständige Verarbeitungsschritte |
| `app/graph.py` | **Graph** – Verbindet Nodes mit Routing-Logik (Edges) |
| `main.py` | **FastAPI Server** – HTTP-Endpunkte |
| `utils/ingest.py` | **RAG Setup** – Dokumente in ChromaDB laden |
| `app/config.py` | **Konfiguration** – API-Keys, Modelle, Pfade |
| `prompts/prompts_config.yaml` | **Prompts** – Alle LLM-Prompts (Hot-Reload) |
| `templates/index.html` | **Frontend** – Chat-Interface mit Bild & Order-Panel |

## Nodes im Detail

### 0. guardrail
Prüft jede Eingabe: blockiert Beleidigungen, Jailbreaks, Spam. Erlaubt Deko-Wünsche.

### 1. classify_and_extract
Erkennt Intent (`greeting`, `order`, `price`, `image`, `info`, `change`, `finalize`, `offtopic`) UND extrahiert Bestellinfos in einem einzigen LLM-Call.

### 2. greet
Begrüßt den Kunden und startet eine neue Session.

### 3. extract_info
Extrahiert Bestellinfos (Anlass, Gäste, Geschmack, Form...) per LLM aus der Nachricht.

### 4. check_complete
Prüft welche Infos noch fehlen. Setzt `order_complete = True` wenn alle 10 Pflichtfelder gefüllt sind.

### 5. ask_next
Fragt nach der nächsten fehlenden Info. Bestätigt zuerst was der Kunde gesagt hat. Smalltalk bei persönlichen Details.

### 6. summarize_order
Fasst die Bestellung zusammen wenn alle Infos da sind.

### 7. retrieve_docs (RAG)
Sucht relevante Dokumente in ChromaDB per Embedding-Similarity (text-embedding-3-small).

### 8. calculate_price
Berechnet den Gesamtpreis basierend auf Bestellinfos + RAG-Kontext. Gibt HTML-Tabelle zurück.

### 9. answer_question
Beantwortet allgemeine Fragen (Allergene, Öffnungszeiten, Lieferung) per RAG.

### 10. generate_image
Generiert Außen- und Querschnittbild mit gpt-image-1. Referenz-Matching aus Portfolio.

### 11. update_order
Verarbeitet Änderungswünsche (Farbe, Form, Größe).

### 12. check_calendar
Prüft Liefertermin-Verfügbarkeit via cal.com API oder SQLite-Kapazität.

### 13. finalize_order
Zeigt Adressformular, speichert Bestellung in SQLite, sendet E-Mail-Bestätigung.

### 14. redirect
Leitet Off-Topic-Fragen zurück zum Kuchen.

## Setup

```bash
# 1. Dependencies installieren
pip install -r requirements.txt

# 2. API-Keys eintragen
cp .env.example .env
# → OPENAI_API_KEY in .env eintragen

# 3. Dokumente in ChromaDB laden
python -m utils.ingest

# 4. Server starten
python main.py
```

Dann öffnen: **http://localhost:5001**

## API Endpunkte

| Endpoint | Methode | Beschreibung |
|----------|---------|-------------|
| `/` | GET | Frontend |
| `/api/chat` | POST | Nachricht senden `{question: "..."}` |
| `/api/chat/stream` | POST | SSE Streaming-Antwort |
| `/api/generate-image` | POST | Bild generieren |
| `/api/reset` | POST | Neues Gespräch |
| `/api/state` | GET | Debug: Aktueller Agent-State |
| `/api/metrics` | GET | Token-Kosten, Latenz |
| `/api/submit-order` | POST | Bestellung abschicken |
| `/order/{id}/pdf` | GET | Bestell-PDF |
| `/admin` | GET | Admin-Panel |

## Technologien

- **FastAPI** – Async HTTP Server
- **OpenAI GPT-4o-mini** – Chat, Intent-Erkennung, Extraktion
- **OpenAI gpt-image-1** – Bildgenerierung (Außen + Querschnitt)
- **OpenAI text-embedding-3-small** – Embeddings für RAG
- **ChromaDB** – Vektor-Datenbank für RAG + Session-Persistenz
- **SQLite** – Bestellungen, Bewertungen, Kapazität
- **LangSmith** – Tracing & Monitoring aller Nodes
- **LangGraph-Pattern** – Nodes + Edges + Shared State
- **Pydantic** – Request-Validierung in FastAPI-Endpunkten

## Admin-Panel

Login unter: http://localhost:5001/admin/login
