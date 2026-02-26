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
import logging
from pathlib import Path
from openai import OpenAI
import chromadb
from state import AgentState, OrderInfo, get_required_fields, get_field_questions
from config import (
    OPENAI_API_KEY, CHAT_MODEL, EMBEDDING_MODEL,
    CHROMA_DB_PATH, COLLECTION_NAME, load_prompts_config,
)
from error_handler import retry_on_transient, parse_llm_json, safe_node

logger = logging.getLogger("cake_dreams")

# --- Clients ---
openai_client = OpenAI(api_key=OPENAI_API_KEY)
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

Path("static/images").mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════
# ZENTRALE LLM-AUFRUFE MIT RETRY
# ═══════════════════════════════════════
@retry_on_transient(max_retries=3, base_delay=1.0)
def _llm_chat(messages: list, temperature: float = 0, max_tokens: int = None) -> str:
    """Zentraler LLM-Aufruf mit Retry-Logik."""
    kwargs = {"model": CHAT_MODEL, "messages": messages, "temperature": temperature}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    response = openai_client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()


@retry_on_transient(max_retries=3, base_delay=1.0)
def _llm_embedding(text: str) -> list:
    """Zentraler Embedding-Aufruf mit Retry-Logik."""
    return openai_client.embeddings.create(
        model=EMBEDDING_MODEL, input=text
    ).data[0].embedding


# ═══════════════════════════════════════
# NODE 1: CLASSIFY INTENT
# ═══════════════════════════════════════
@safe_node(fallback_response="Wie kann ich Ihnen helfen?")
def classify_intent(state: AgentState) -> AgentState:
    """Erkennt was der Kunde will: bestellen, Preis wissen, Bild, Info, etc."""

    config = load_prompts_config()
    system_prompt = config["prompts"]["classify_intent"]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content":
            f"Gesprächsverlauf:\n{format_history(state.get('messages', []))}\n\n"
            f"Neue Nachricht: {state['user_input']}"}
    ]

    intent = _llm_chat(messages, temperature=0, max_tokens=20).lower()

    valid = ["greeting", "order", "price", "image", "info", "change", "offtopic"]
    if intent not in valid:
        intent = "order"

    logger.info(f"Intent: {intent}")
    state["intent"] = intent
    return state


# ═══════════════════════════════════════
# NODE 2: GREET
# ═══════════════════════════════════════
@safe_node()
def greet(state: AgentState) -> AgentState:
    """Begrüßt den Kunden freundlich."""
    config = load_prompts_config()
    state["response"] = config["prompts"]["greet"]
    return state


# ═══════════════════════════════════════
# NODE 3: EXTRACT INFO
# ═══════════════════════════════════════
@safe_node(fallback_response="Ich konnte Ihre Angaben nicht verarbeiten. Bitte versuchen Sie es erneut.")
def extract_info(state: AgentState) -> AgentState:
    """Extrahiert Bestellinfos aus der Kundennachricht per LLM."""

    config = load_prompts_config()
    system_prompt = config["prompts"]["extract_info"]
    order_info = state.get("order_info", {})

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content":
            f"Gesprächsverlauf:\n{format_history(state.get('messages', []))}\n\n"
            f"Neue Nachricht: {state['user_input']}"}
    ]

    raw = _llm_chat(messages, temperature=0)

    # JSON parsen mit Retry-Feedback bei Fehler
    def retry_call(retry_messages):
        return _llm_chat(retry_messages, temperature=0)

    try:
        new_info = parse_llm_json(
            raw, retry_func=retry_call, max_retries=1, context_messages=messages
        )
    except Exception as e:
        logger.warning(f"JSON-Extraktion fehlgeschlagen, fahre ohne neue Infos fort: {e}")
        new_info = {}

    # Merge: neue Infos überschreiben alte
    for key, value in new_info.items():
        if isinstance(value, str) and value.strip():
            order_info[key] = value.strip()

    state["order_info"] = order_info
    logger.info(f"Order Info: {order_info}")
    return state


# ═══════════════════════════════════════
# NODE 4: CHECK COMPLETE
# ═══════════════════════════════════════
@safe_node()
def check_complete(state: AgentState) -> AgentState:
    """Prüft welche Bestellinfos noch fehlen."""

    required = get_required_fields()
    order_info = state.get("order_info", {})
    missing = [f for f in required if f not in order_info or not order_info.get(f)]

    state["missing_fields"] = missing
    state["order_complete"] = len(missing) == 0

    logger.info(f"Complete: {state['order_complete']} | Missing: {missing}")
    return state


# ═══════════════════════════════════════
# NODE 5: ASK NEXT QUESTION
# ═══════════════════════════════════════
@safe_node(fallback_response="Was möchten Sie mir noch zu Ihrem Kuchen erzählen?")
def ask_next(state: AgentState) -> AgentState:
    """Fragt nach der nächsten fehlenden Info. Wählt kontextbasiert die natürlichste Frage."""

    config = load_prompts_config()
    system_prompt = config["prompts"]["ask_next"]
    field_questions = get_field_questions()

    missing = state.get("missing_fields", [])
    order_info = state.get("order_info", {})
    last_input = state.get("user_input", "")
    history = format_history(state.get("messages", [])[-8:])

    # Alle noch fehlenden Fragen aufzählen – LLM wählt die passendste
    missing_questions = "\n".join(
        f"- {field}: {field_questions.get(field, field)}"
        for field in missing
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content":
            f"Gesprächsverlauf:\n{history}\n\n"
            f"Letzte Kundennachricht: '{last_input}'\n"
            f"Bisher gesammelt: {json.dumps(order_info, ensure_ascii=False)}\n\n"
            f"Noch fehlende Informationen (wähle die eine natürlichste):\n{missing_questions}"}
    ]

    state["response"] = _llm_chat(messages, temperature=0.4, max_tokens=150)
    return state


# ═══════════════════════════════════════
# NODE 6: SUMMARIZE ORDER
# ═══════════════════════════════════════
@safe_node()
def summarize_order(state: AgentState) -> AgentState:
    """Fasst die komplette Bestellung zusammen wenn alle Infos da sind."""

    order_info = state.get("order_info", {})

    labels = {
        "geschmack": "Kuchen", "gaeste": "Für", "form": "Form",
        "schichten": "Schichten", "fuellung": "Füllung",
        "dekoration": "Dekoration", "farbe": "Farbe", "anlass": "Anlass"
    }

    summary_parts = []
    for key, label in labels.items():
        if order_info.get(key):
            summary_parts.append(f"{label}: {order_info[key]}")

    summary = ", ".join(summary_parts)

    state["response"] = (
        f"Ihre Bestellung ist komplett! Hier die Zusammenfassung: {summary}. "
        f"Möchten Sie den Preis wissen oder soll ich ein Vorschaubild generieren?"
    )
    return state


# ═══════════════════════════════════════
# NODE 7: RETRIEVE DOCS (RAG)
# ═══════════════════════════════════════
@safe_node(fallback_response="Ich konnte leider keine Informationen abrufen.")
def retrieve_docs(state: AgentState) -> AgentState:
    """Sucht relevante Dokumenten-Chunks in ChromaDB."""

    query = state.get("user_input", "")

    try:
        query_embedding = _llm_embedding(query)
        results = collection.query(query_embeddings=[query_embedding], n_results=5)
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        context_parts = []
        for doc, meta in zip(docs, metas):
            source = meta.get("source", "unbekannt")
            context_parts.append(f"[{source}] {doc}")

        state["context"] = "\n\n---\n\n".join(context_parts)
        state["sources"] = metas
        logger.info(f"Retrieved {len(docs)} chunks")

    except Exception as e:
        logger.error(f"RAG Fehler: {e}")
        state["context"] = ""
        state["sources"] = []

    return state


# ═══════════════════════════════════════
# NODE 8: CALCULATE PRICE
# ═══════════════════════════════════════
@safe_node(fallback_response="Ich konnte den Preis leider nicht berechnen. Rufen Sie uns an unter 0221-1234567.")
def calculate_price(state: AgentState) -> AgentState:
    """Berechnet den Preis basierend auf Bestellinfos + Dokument-Kontext."""

    config = load_prompts_config()
    system_prompt = config["prompts"]["calculate_price"]
    order_info = state.get("order_info", {})
    context = state.get("context", "")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content":
            f"KONTEXT (Preisliste):\n{context}\n\n"
            f"BESTELLDETAILS:\n{json.dumps(order_info, ensure_ascii=False)}\n\n"
            f"Berechne den Gesamtpreis."}
    ]

    state["response"] = _llm_chat(messages, temperature=0)
    return state


# ═══════════════════════════════════════
# NODE 9: ANSWER QUESTION (Info)
# ═══════════════════════════════════════
@safe_node(fallback_response="Dazu kann ich leider keine Auskunft geben. Rufen Sie uns an unter 0221-1234567.")
def answer_question(state: AgentState) -> AgentState:
    """Beantwortet allgemeine Fragen basierend auf RAG-Kontext."""

    config = load_prompts_config()
    system_prompt = config["prompts"]["answer_question"]
    context = state.get("context", "")
    question = state.get("user_input", "")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"KONTEXT:\n{context}\n\nFRAGE: {question}"}
    ]

    state["response"] = _llm_chat(messages, temperature=0.3)
    return state


# ═══════════════════════════════════════
# NODE 10: GENERATE IMAGE
# ═══════════════════════════════════════
@safe_node(fallback_response="Die Bildgenerierung hat leider nicht geklappt. Beschreiben Sie Ihren Wunschkuchen nochmal genauer.")
def generate_image(state: AgentState) -> AgentState:
    """Generiert ein Kuchenbild basierend auf den gesammelten Bestellinfos."""

    order_info = state.get("order_info", {})
    messages_history = state.get("messages", [])

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
        logger.info(f"Bild generiert: {filepath}")

    except Exception as e:
        logger.error(f"Bildgenerierung fehlgeschlagen: {e}")
        state["image_url"] = None
        state["response"] = "Die Bildgenerierung hat leider nicht geklappt. Beschreiben Sie Ihren Wunschkuchen nochmal genauer."

    return state


# ═══════════════════════════════════════
# NODE 11: UPDATE ORDER (Änderungen)
# ═══════════════════════════════════════
@safe_node(fallback_response="Was möchten Sie an Ihrer Bestellung ändern oder hinzufügen?")
def update_order(state: AgentState) -> AgentState:
    """Verarbeitet Änderungswünsche oder Ergänzungen an der bestehenden Bestellung."""

    order_info_before = dict(state.get("order_info", {}))
    state = extract_info(state)
    order_info_after = state.get("order_info", {})

    # Prüfen ob tatsächlich neue Infos extrahiert wurden
    new_keys = {k for k, v in order_info_after.items()
                if k not in order_info_before or order_info_before[k] != v}

    if not new_keys:
        # Nichts extrahiert → fragen was der Kunde möchte
        config = load_prompts_config()
        field_questions = get_field_questions()
        current = json.dumps(order_info_after, ensure_ascii=False) if order_info_after else "noch keine"

        messages = [
            {"role": "system", "content":
                "Du bist ein freundlicher Kuchenberater bei Kidstorte. "
                "Der Kunde möchte etwas an seiner Bestellung ändern oder hinzufügen, "
                "hat aber noch nicht gesagt was. Frage freundlich und konkret was er ändern/ergänzen möchte. "
                "Nenne dabei die Möglichkeiten: Geschmack, Form, Schichten, Füllung, Dekoration, Farbe. "
                "Maximal 2 Sätze. Kein Markdown."},
            {"role": "user", "content":
                f"Kunde: '{state.get('user_input', '')}'\n"
                f"Bisherige Bestellung: {current}"}
        ]
        state["response"] = _llm_chat(messages, temperature=0.3, max_tokens=100)
    else:
        changed = ", ".join(new_keys)
        state["response"] = (
            f"Perfekt, ich habe {changed} für Sie aktualisiert! "
            f"Möchten Sie noch etwas ändern oder soll ich den aktualisierten Preis berechnen?"
        )
        # check_complete neu ausführen
        state = check_complete(state)

    return state


# ═══════════════════════════════════════
# NODE 12: REDIRECT (Off-Topic)
# ═══════════════════════════════════════
@safe_node()
def redirect(state: AgentState) -> AgentState:
    """Leitet höflich zurück zum Thema."""
    config = load_prompts_config()
    state["response"] = config["prompts"]["redirect"]
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
    """Baut eine visuelle Beschreibung für die Bildgenerierung."""
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
            config = load_prompts_config()
            system_prompt = config["prompts"].get("image_description",
                "Beschreibe den Kuchen aus dem Gespräch in EINEM Satz. "
                "Visuell detailliert: Geschmack, Form, Farbe, Dekoration. Nur den Kuchen.")
            result = _llm_chat(
                [{"role": "system", "content": system_prompt}] + messages[-10:],
                temperature=0
            )
            return result
        except Exception as e:
            logger.warning(f"Fallback-Bildbeschreibung fehlgeschlagen: {e}")

    return "Ein schöner Geburtstagskuchen mit Dekoration"
