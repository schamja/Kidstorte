"""
Nodes – Jeder Node ist ein eigenständiger Schritt im Agenten.
Jeder Node bekommt den State, verarbeitet ihn, und gibt den aktualisierten State zurück.

Graph-Übersicht:
    START → classify_intent
      ├── greeting   → greet
      ├── order      → extract_info → check_complete → ask_next / summarize
      ├── price      → retrieve_docs → calculate_price
      ├── image      → generate_image
      ├── info       → retrieve_docs → answer_question
      ├── change     → update_order
      └── offtopic   → redirect
"""

import json
import uuid
import base64
from pathlib import Path
from openai import OpenAI
import chromadb
from state import AgentState, OrderInfo, REQUIRED_FIELDS, FIELD_QUESTIONS
from config import OPENAI_API_KEY, CHAT_MODEL, EMBEDDING_MODEL, CHROMA_DB_PATH, COLLECTION_NAME

# --- Clients ---
openai_client = OpenAI(api_key=OPENAI_API_KEY)
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

Path("static/images").mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════
# NODE 1: CLASSIFY INTENT
# ═══════════════════════════════════════
def classify_intent(state: AgentState) -> AgentState:
    """Erkennt was der Kunde will: bestellen, Preis wissen, Bild, Info, etc."""

    messages = [
        {"role": "system", "content": """
Klassifiziere die Kundenachricht in GENAU eine Kategorie.
Antworte NUR mit dem Kategorie-Namen, nichts anderes.

Kategorien:
- greeting: Begrüßung, Hallo, Hi
- order: Kunde will bestellen, Kuchen aussuchen, Geburtstag, Hochzeit, Feier
- price: Fragt nach Preis, Kosten, was kostet, wie teuer
- image: Will ein Bild sehen, zeig mir, visualisieren, Foto, aussehen, Vorschau
- info: Fragt nach Zutaten, Allergenen, Öffnungszeiten, Lieferung, allgemeine Fragen
- change: Will etwas an der bisherigen Auswahl ändern (Farbe, Form, Größe ändern)
- offtopic: Hat nichts mit Kuchen oder dem Laden zu tun

Berücksichtige den Gesprächsverlauf: Wenn der Kunde schon bestellt und jetzt Details nennt (z.B. "Schokolade", "rund", "3 Schichten"), ist es immer noch "order".
"""},
        {"role": "user", "content": f"Gesprächsverlauf:\n{format_history(state.get('messages', []))}\n\nNeue Nachricht: {state['user_input']}"}
    ]

    response = openai_client.chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=0, max_tokens=20
    )
    intent = response.choices[0].message.content.strip().lower()

    # Validierung
    valid = ["greeting", "order", "price", "image", "info", "change", "offtopic"]
    if intent not in valid:
        intent = "order"  # Default: wenn unklar, behandle als Bestellung

    print(f"🧠 Intent: {intent}")
    state["intent"] = intent
    return state


# ═══════════════════════════════════════
# NODE 2: GREET
# ═══════════════════════════════════════
def greet(state: AgentState) -> AgentState:
    """Begrüßt den Kunden freundlich."""
    state["response"] = "Hallo und willkommen bei Cake Dreams! Wie kann ich Ihnen helfen?"
    return state


# ═══════════════════════════════════════
# NODE 3: EXTRACT INFO
# ═══════════════════════════════════════
def extract_info(state: AgentState) -> AgentState:
    """Extrahiert Bestellinfos aus der Kundennachricht per LLM."""

    order_info = state.get("order_info", {})

    messages = [
        {"role": "system", "content": """
Extrahiere Bestellinformationen aus dem Gesprächsverlauf.
Antworte NUR mit einem JSON-Objekt. Keine Erklärungen.

Felder (nur füllen wenn der Kunde es EXPLIZIT gesagt hat, sonst weglassen):
{
    "anlass": "z.B. Geburtstag, Hochzeit",
    "gaeste": "z.B. 20 Kinder, 30 Leute",
    "geschmack": "z.B. Schokolade, Vanille",
    "form": "z.B. rund, eckig, Herzform",
    "schichten": "z.B. 2, 3",
    "fuellung": "z.B. Himbeere, Schokolade",
    "dekoration": "z.B. Fondant, Motivkuchen Elsa",
    "farbe": "z.B. rosa, blau"
}

Beispiel Antwort: {"anlass": "Geburtstag", "gaeste": "20 Kinder", "geschmack": "Schokolade"}
"""},
        {"role": "user", "content": f"Gesprächsverlauf:\n{format_history(state.get('messages', []))}\n\nNeue Nachricht: {state['user_input']}"}
    ]

    response = openai_client.chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=0
    )

    try:
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        new_info = json.loads(raw)
    except:
        new_info = {}

    # Merge: neue Infos überschreiben alte
    for key, value in new_info.items():
        if value and value.strip():
            order_info[key] = value.strip()

    state["order_info"] = order_info
    print(f"📋 Order Info: {order_info}")
    return state


# ═══════════════════════════════════════
# NODE 4: CHECK COMPLETE
# ═══════════════════════════════════════
def check_complete(state: AgentState) -> AgentState:
    """Prüft welche Bestellinfos noch fehlen."""

    order_info = state.get("order_info", {})
    missing = [f for f in REQUIRED_FIELDS if f not in order_info or not order_info.get(f)]

    state["missing_fields"] = missing
    state["order_complete"] = len(missing) == 0

    print(f"✅ Complete: {state['order_complete']} | Missing: {missing}")
    return state


# ═══════════════════════════════════════
# NODE 5: ASK NEXT QUESTION
# ═══════════════════════════════════════
def ask_next(state: AgentState) -> AgentState:
    """Fragt nach der nächsten fehlenden Info. Bestätigt zuerst was der Kunde gesagt hat."""

    missing = state.get("missing_fields", [])
    order_info = state.get("order_info", {})

    # Was hat der Kunde gerade gesagt? Kurze Bestätigung
    last_input = state.get("user_input", "")

    # Nächste fehlende Frage
    next_field = missing[0] if missing else None
    next_question = FIELD_QUESTIONS.get(next_field, "")

    # Bestätigung + nächste Frage per LLM formulieren
    messages = [
        {"role": "system", "content":
            "Du bist ein freundlicher Kuchenberater. Bestätige KURZ (1 Satz) was der Kunde gesagt hat, "
            "dann stelle die nächste Frage. Kein Markdown. Maximal 2 Sätze gesamt. "
            "Sei natürlich und warmherzig."
        },
        {"role": "user", "content":
            f"Kunde hat gesagt: '{last_input}'\n"
            f"Bisher gesammelt: {json.dumps(order_info, ensure_ascii=False)}\n"
            f"Nächste Frage die du stellen musst: {next_question}"
        }
    ]

    response = openai_client.chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=0.4, max_tokens=150
    )

    state["response"] = response.choices[0].message.content
    return state


# ═══════════════════════════════════════
# NODE 6: SUMMARIZE ORDER
# ═══════════════════════════════════════
def summarize_order(state: AgentState) -> AgentState:
    """Fasst die komplette Bestellung zusammen wenn alle Infos da sind."""

    order_info = state.get("order_info", {})

    summary_parts = []
    if order_info.get("geschmack"):
        summary_parts.append(f"Kuchen: {order_info['geschmack']}")
    if order_info.get("gaeste"):
        summary_parts.append(f"Für: {order_info['gaeste']}")
    if order_info.get("form"):
        summary_parts.append(f"Form: {order_info['form']}")
    if order_info.get("schichten"):
        summary_parts.append(f"Schichten: {order_info['schichten']}")
    if order_info.get("fuellung"):
        summary_parts.append(f"Füllung: {order_info['fuellung']}")
    if order_info.get("dekoration"):
        summary_parts.append(f"Dekoration: {order_info['dekoration']}")
    if order_info.get("farbe"):
        summary_parts.append(f"Farbe: {order_info['farbe']}")
    if order_info.get("anlass"):
        summary_parts.append(f"Anlass: {order_info['anlass']}")

    summary = ", ".join(summary_parts)

    state["response"] = (
        f"Ihre Bestellung ist komplett! Hier die Zusammenfassung: {summary}. "
        f"Möchten Sie den Preis wissen oder soll ich ein Vorschaubild generieren?"
    )
    return state


# ═══════════════════════════════════════
# NODE 7: RETRIEVE DOCS (RAG)
# ═══════════════════════════════════════
def retrieve_docs(state: AgentState) -> AgentState:
    """Sucht relevante Dokumenten-Chunks in ChromaDB."""

    query = state.get("user_input", "")

    try:
        query_embedding = openai_client.embeddings.create(
            model=EMBEDDING_MODEL, input=query
        ).data[0].embedding

        results = collection.query(query_embeddings=[query_embedding], n_results=5)
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        context_parts = []
        for doc, meta in zip(docs, metas):
            source = meta.get("source", "unbekannt")
            context_parts.append(f"[{source}] {doc}")

        state["context"] = "\n\n---\n\n".join(context_parts)
        state["sources"] = metas
        print(f"📚 Retrieved {len(docs)} chunks")

    except Exception as e:
        print(f"❌ RAG Fehler: {e}")
        state["context"] = ""
        state["sources"] = []

    return state


# ═══════════════════════════════════════
# NODE 8: CALCULATE PRICE
# ═══════════════════════════════════════
def calculate_price(state: AgentState) -> AgentState:
    """Berechnet den Preis basierend auf Bestellinfos + Dokument-Kontext."""

    order_info = state.get("order_info", {})
    context = state.get("context", "")

    messages = [
        {"role": "system", "content":
            "Du bist der Preisrechner von Cake Dreams. "
            "Berechne den Gesamtpreis basierend auf den Bestelldetails und dem Kontext. "
            "Zeige die Berechnung als Fließtext (kein Markdown). "
            "Grundpreis + alle Extras einzeln aufführen = Gesamtpreis. "
            "Nutze NUR Preise aus dem Kontext. Erfinde KEINE Preise."
        },
        {"role": "user", "content":
            f"KONTEXT (Preisliste):\n{context}\n\n"
            f"BESTELLDETAILS:\n{json.dumps(order_info, ensure_ascii=False)}\n\n"
            f"Berechne den Gesamtpreis."
        }
    ]

    response = openai_client.chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=0
    )

    state["response"] = response.choices[0].message.content
    return state


# ═══════════════════════════════════════
# NODE 9: ANSWER QUESTION (Info)
# ═══════════════════════════════════════
def answer_question(state: AgentState) -> AgentState:
    """Beantwortet allgemeine Fragen basierend auf RAG-Kontext."""

    context = state.get("context", "")
    question = state.get("user_input", "")

    messages = [
        {"role": "system", "content":
            "Du bist der Berater von Cake Dreams. Beantworte die Frage basierend auf dem Kontext. "
            "Kurz und freundlich (2-3 Sätze). Kein Markdown. "
            "Wenn die Info nicht im Kontext steht: 'Dazu kann ich keine Auskunft geben. Rufen Sie uns an unter 0221-1234567.'"
        },
        {"role": "user", "content": f"KONTEXT:\n{context}\n\nFRAGE: {question}"}
    ]

    response = openai_client.chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=0.3
    )

    state["response"] = response.choices[0].message.content
    return state


# ═══════════════════════════════════════
# NODE 10: GENERATE IMAGE
# ═══════════════════════════════════════
def generate_image(state: AgentState) -> AgentState:
    """Generiert ein Kuchenbild basierend auf den gesammelten Bestellinfos."""

    order_info = state.get("order_info", {})
    messages_history = state.get("messages", [])

    # Zusammenfassung erstellen
    description = build_image_description(order_info, messages_history)

    cake_prompt = (
        f"Professionelles Food-Fotografie Produktbild eines Kuchens: {description}. "
        f"Weißer sauberer Hintergrund, Studiolicht, appetitlich, "
        f"hochwertige Bäckerei-Qualität, fotorealistisch, detailliert."
    )

    try:
        response = openai_client.images.generate(
            model="gpt-image-1",
            prompt=cake_prompt,
            size="1024x1024"
        )
        image_data = response.data[0].b64_json
        filename = f"{uuid.uuid4().hex}.png"
        filepath = f"static/images/{filename}"

        with open(filepath, "wb") as f:
            f.write(base64.b64decode(image_data))

        state["image_url"] = f"/static/images/{filename}"
        state["response"] = "Hier ist eine Vorschau Ihres Wunschkuchens! Das finale Produkt kann leicht abweichen. Gefällt Ihnen das Design?"
        print(f"🖼️ Bild generiert: {filepath}")

    except Exception as e:
        print(f"❌ Bildgenerierung fehlgeschlagen: {e}")
        state["image_url"] = None
        state["response"] = "Die Bildgenerierung hat leider nicht geklappt. Beschreiben Sie Ihren Wunschkuchen nochmal genauer."

    return state


# ═══════════════════════════════════════
# NODE 11: UPDATE ORDER (Änderungen)
# ═══════════════════════════════════════
def update_order(state: AgentState) -> AgentState:
    """Verarbeitet Änderungswünsche an der bestehenden Bestellung."""

    # extract_info übernimmt das Mergen automatisch
    state = extract_info(state)
    order_info = state.get("order_info", {})

    state["response"] = (
        f"Klar, ich habe die Änderung übernommen! "
        f"Möchten Sie ein neues Vorschaubild sehen oder den aktualisierten Preis wissen?"
    )
    return state


# ═══════════════════════════════════════
# NODE 12: REDIRECT (Off-Topic)
# ═══════════════════════════════════════
def redirect(state: AgentState) -> AgentState:
    """Leitet höflich zurück zum Thema."""
    state["response"] = "Ich bin Ihr Kuchenberater und helfe gerne bei der Auswahl. Wie kann ich Ihnen bei Ihrer Kuchenbestellung helfen?"
    return state


# ═══════════════════════════════════════
# HILFSFUNKTIONEN
# ═══════════════════════════════════════
def format_history(messages, max_messages=10):
    """Formatiert den Gesprächsverlauf als String."""
    recent = messages[-max_messages:] if messages else []
    lines = []
    for msg in recent:
        role = "Kunde" if msg["role"] == "user" else "Berater"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines) if lines else "(Noch kein Gespräch)"


def build_image_description(order_info, messages):
    """Baut eine visuelle Beschreibung für DALL-E."""
    parts = []
    if order_info.get("geschmack"):
        parts.append(f"{order_info['geschmack']}kuchen")
    if order_info.get("form"):
        parts.append(f"{order_info['form']}e Form")
    if order_info.get("schichten"):
        parts.append(f"{order_info['schichten']} Schichten")
    if order_info.get("fuellung"):
        parts.append(f"Füllung: {order_info['fuellung']}")
    if order_info.get("dekoration"):
        parts.append(f"Dekoration: {order_info['dekoration']}")
    if order_info.get("farbe"):
        parts.append(f"Farbe: {order_info['farbe']}")

    if parts:
        return ", ".join(parts)

    # Fallback: aus letzten Nachrichten zusammenbauen
    if messages:
        try:
            resp = openai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content":
                        "Beschreibe den Kuchen aus dem Gespräch in EINEM Satz. "
                        "Visuell detailliert: Geschmack, Form, Farbe, Dekoration. Nur den Kuchen."},
                ] + messages[-10:],
                temperature=0
            )
            return resp.choices[0].message.content
        except:
            pass

    return "Ein schöner Geburtstagskuchen mit Dekoration"
