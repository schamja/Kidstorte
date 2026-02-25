<<<<<<< HEAD
# 🎂 Cake Dreams – LangGraph Agent

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
| `state.py` | **Shared State** – Das zentrale Datenobjekt (OrderInfo, AgentState) |
| `nodes.py` | **Nodes** – 12 eigenständige Verarbeitungsschritte |
| `graph.py` | **Graph** – Verbindet Nodes mit Routing-Logik (Edges) |
| `main.py` | **FastAPI Server** – HTTP-Endpunkte |
| `ingest.py` | **RAG Setup** – Dokumente in ChromaDB laden |
| `config.py` | **Konfiguration** – API-Keys, Modelle, Pfade |
| `templates/index.html` | **Frontend** – Chat-Interface mit Bild & Order-Panel |

## Nodes im Detail

### 1. classify_intent
Erkennt per LLM was der Kunde will: `greeting`, `order`, `price`, `image`, `info`, `change`, `offtopic`

### 2. greet
Begrüßt den Kunden.

### 3. extract_info
Extrahiert Bestellinfos (Anlass, Gäste, Geschmack, Form...) per LLM aus der Nachricht.

### 4. check_complete
Prüft welche Infos noch fehlen. Setzt `order_complete = True` wenn alles da ist.

### 5. ask_next
Fragt nach der nächsten fehlenden Info. Bestätigt zuerst was der Kunde gesagt hat.

### 6. summarize_order
Fasst die Bestellung zusammen wenn alle Infos da sind.

### 7. retrieve_docs (RAG)
Sucht relevante Dokumente in ChromaDB per Embedding-Similarity.

### 8. calculate_price
Berechnet den Gesamtpreis basierend auf Bestellinfos + RAG-Kontext.

### 9. answer_question
Beantwortet allgemeine Fragen (Allergene, Öffnungszeiten, Lieferung) per RAG.

### 10. generate_image
Generiert ein Kuchenbild mit DALL-E basierend auf den Bestellinfos.

### 11. update_order
Verarbeitet Änderungswünsche (Farbe, Form, Größe).

### 12. redirect
Leitet Off-Topic-Fragen zurück zum Kuchen.

## Setup

```bash
# 1. Dependencies installieren
pip install -r requirements.txt

# 2. API-Key eintragen
cp .env.example .env
# → OPENAI_API_KEY in .env eintragen

# 3. Dokumente in ChromaDB laden
python ingest.py

# 4. Server starten
python main.py
```

Dann öffnen: **http://localhost:5001**

## API Endpunkte

| Endpoint | Methode | Beschreibung |
|----------|---------|-------------|
| `/` | GET | Frontend |
| `/api/chat` | POST | Nachricht senden `{question: "..."}` |
| `/api/generate-image` | POST | Bild generieren |
| `/api/reset` | POST | Neues Gespräch |
| `/api/state` | GET | Debug: Aktueller Agent-State |

## Technologien

- **FastAPI** – Async HTTP Server
- **OpenAI GPT-4o-mini** – Chat & Intent-Erkennung
- **OpenAI text-embedding-3-small** – Embeddings für RAG
- **OpenAI DALL-E (gpt-image-1)** – Bildgenerierung
- **ChromaDB** – Vektor-Datenbank für Dokumente
- **LangGraph-Pattern** – Nodes + Edges + Shared State
=======
# Kidstorte
>>>>>>> 64ef9d417ef8e6d1eff77902e78adcc1386746eb
