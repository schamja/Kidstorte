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
import os
import requests
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
import chromadb
from app.state import AgentState, OrderInfo, get_required_fields, get_field_questions
from app.config import (
    OPENAI_API_KEY, CHAT_MODEL, IMAGE_MODEL, EMBEDDING_MODEL,
    CHROMA_DB_PATH, COLLECTION_NAME, load_prompts_config,
    VISION_MODEL, REFERENCE_IMAGE_DIR,
)
from utils.error_handler import retry_on_transient, parse_llm_json, safe_node
from monitoring.tracing import trace_node, trace_llm_call, trace_image_gen

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")

logger = logging.getLogger("cake_dreams")

# --- Clients ---
# Schneller Client für Text-Anfragen (Chat, Classify, Extract)
openai_client = OpenAI(
    api_key=OPENAI_API_KEY,
    timeout=30.0,       # max 30s pro Request (Chat ist schnell)
    max_retries=1,
)

# Langsamer Client für Bildgenerierung (gpt-image-1 braucht 30-90s)
openai_image_client = OpenAI(
    api_key=OPENAI_API_KEY,
    timeout=120.0,      # 2 Minuten für Bildgenerierung
    max_retries=2,      # 2 Retries bei Timeout
)
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

Path("static/images").mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════
# ZENTRALE LLM-AUFRUFE MIT RETRY
# ═══════════════════════════════════════
@retry_on_transient(max_retries=3, base_delay=5.0)
def _llm_chat(messages: list, temperature: float = 0, max_tokens: int = None) -> str:
    """Zentraler LLM-Aufruf mit Retry-Logik + LangSmith Tracing.
    Rate Limit bei 5 RPM → Delays: 5s → 10s → 20s"""
    import time as _time
    t0 = _time.time()
    kwargs = {"model": CHAT_MODEL, "messages": messages, "temperature": temperature}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    response = openai_client.chat.completions.create(**kwargs)
    result = response.choices[0].message.content.strip()
    # LangSmith: LLM-Call tracken
    duration_ms = (_time.time() - t0) * 1000
    trace_llm_call("llm_chat", messages, result, model=CHAT_MODEL, duration_ms=duration_ms)
    return result


@retry_on_transient(max_retries=2, base_delay=0.3)
def _llm_embedding(text: str) -> list:
    """Zentraler Embedding-Aufruf mit Retry-Logik."""
    return openai_client.embeddings.create(
        model=EMBEDDING_MODEL, input=text
    ).data[0].embedding


# ═══════════════════════════════════════
# NODE 0: GUARDRAIL (Eingabe-Prüfung)
# ═══════════════════════════════════════
@trace_node("guardrail")
@safe_node(fallback_response="Ich bin Ihr Kuchenberater bei Kidstorte. Bitte stellen Sie nur Fragen zu unserem Sortiment. 🎂")
def guardrail(state: AgentState) -> AgentState:
    """
    Prüft jede Eingabe bevor sie den Agenten erreicht.
    Blockiert: Beleidigungen, Jailbreak-Versuche, Spam.
    Erlaubt: Alles rund um Kuchen, Bestellungen, Preise, Begrüßungen.

    PERFORMANCE-FIX (Plan B): Kein LLM-Call mehr — rein regex/keyword-basiert.
    Spart 1 OpenAI-Request pro Turn (kritisch bei niedrigem Rate-Limit).
    Trade-off: keine semantische Erkennung subtiler Jailbreaks. Für die meisten
    Fälle (offensichtliche Manipulation, Spam, Beleidigungen) reicht Regex aus.
    Bei echtem Bedarf später den LLM-Check wieder einkommentieren.
    """
    import re as _re
    user_input = state.get("user_input", "").strip()
    state["guardrail_blocked"] = False

    # Leere Eingabe
    if not user_input:
        state["guardrail_blocked"] = True
        state["response"] = "Bitte geben Sie eine Nachricht ein. Wie kann ich Ihnen helfen?"
        return state

    # Spam-Schutz: Eingabe zu lang
    if len(user_input) > 800:
        state["guardrail_blocked"] = True
        state["response"] = (
            "Ihre Nachricht ist leider zu lang. "
            "Bitte fassen Sie sich kürzer – ich helfe Ihnen gerne bei Ihrer Kuchenbestellung!"
        )
        return state

    user_low = user_input.lower()

    # FAIL-OPEN: Wenn klar Kuchen/Bestell-Vokabular enthalten → SOFORT durchlassen
    # (vor allen Block-Checks — fängt False-Positives ab)
    cake_domain_keywords = (
        "kuchen", "torte", "fondant", "deko", "dekoration", "schicht",
        "füllung", "fuellung", "geschmack", "anlass", "geburtstag", "hochzeit",
        "form", "rund", "eckig", "herz", "preis", "lieferung", "abholung",
        "termin", "allergie", "beschriftung", "vorschau", "bild",
        "sportwagen", "auto", "figur", "ronaldo", "elsa", "spiderman",
        "einhorn", "dino", "krone", "rakete",
        "farbe", "rosa", "rose", "pink", "blau", "rot", "grün", "gelb",
        "schoko", "vanille", "erdbeer", "zitrone", "himbeer",
        "möchte", "will", "hätte", "gerne", "bitte", "hallo", "guten",
        "tag", "morgen", "abend", "danke", "ja", "nein", "ok", "klar",
    )
    if any(kw in user_low for kw in cake_domain_keywords):
        return state  # Kuchen-Kontext erkannt — definitiv erlauben

    # Jailbreak-/Manipulation-Patterns (regex)
    jailbreak_patterns = (
        r"ignore (your |the |all )?(instructions|prompts?|rules)",
        r"forget (your |the |all )?(instructions|prompts?|rules)",
        r"vergiss (deine|alle) (anweisungen|regeln|prompts?)",
        r"act as (a |an )?",
        r"du bist jetzt (ein|eine)",
        r"jailbreak",
        r"system prompt",
        r"reveal (your |the )?prompt",
    )
    for pattern in jailbreak_patterns:
        if _re.search(pattern, user_low):
            state["guardrail_blocked"] = True
            state["response"] = (
                "Diese Nachricht kann ich leider nicht verarbeiten. "
                "Ich helfe Ihnen gerne bei Ihrer Kuchenbestellung! 🎂"
            )
            logger.warning(f"Guardrail BLOCKIERT (jailbreak): '{user_input[:60]}'")
            return state

    # Beleidigungen / üble Wörter — knappe Blacklist (gröbste Fälle)
    slur_patterns = (
        r"\b(arschloch|wichser|hurensohn|fick dich|verpiss dich|scheiß[ae])\b",
        r"\b(fuck you|asshole|bitch)\b",
    )
    for pattern in slur_patterns:
        if _re.search(pattern, user_low):
            state["guardrail_blocked"] = True
            state["response"] = (
                "Bitte bleiben Sie höflich. Ich helfe Ihnen gerne bei Ihrer "
                "Kuchenbestellung! 🎂"
            )
            logger.warning(f"Guardrail BLOCKIERT (slur): '{user_input[:60]}'")
            return state

    # Spam: extrem wenige verschiedene Zeichen + lang (z.B. "aaaaaaaaaa...")
    if len(user_input) > 20 and len(set(user_low)) <= 3:
        state["guardrail_blocked"] = True
        state["response"] = (
            "Diese Nachricht sieht nicht nach einer echten Frage aus. "
            "Wie kann ich Ihnen mit Ihrer Kuchenbestellung helfen? 🎂"
        )
        logger.warning(f"Guardrail BLOCKIERT (spam): '{user_input[:60]}'")
        return state

    # Default: durchlassen (fail-open)
    return state


# ═══════════════════════════════════════
# NODE 1: CLASSIFY + EXTRACT (kombiniert für Speed)
# ═══════════════════════════════════════
@trace_node("classify_and_extract")
@safe_node(fallback_response="Wie kann ich Ihnen helfen?")
def classify_and_extract(state: AgentState) -> AgentState:
    """Erkennt Intent UND extrahiert Bestellinfos in einem
    einzigen LLM-Call."""

    config = load_prompts_config()
    classify_prompt = config["prompts"]["classify_intent"]
    extract_prompt = config["prompts"]["extract_info"]

    combined_prompt = (
        f"{classify_prompt}\n\n"
        "ZUSÄTZLICH: Extrahiere IMMER Bestellinfos aus der NEUEN Nachricht — EGAL welcher Intent!\n"
        "Auch bei 'finalize', 'image' oder 'info': Wenn der Kunde Bestelldetails nennt "
        "(z.B. 'ja Happy Birthday', 'ich will abholen', 'keine Allergien'), "
        "MÜSSEN diese in 'extracted' stehen!\n"
        f"{extract_prompt}\n\n"
        "Antworte NUR mit einem JSON-Objekt in diesem Format:\n"
        '{"intent": "greeting|order|price|image|info|change|finalize|offtopic", '
        '"extracted": {"anlass": "...", "gaeste": "..."} }\n'
        "extracted = {} NUR wenn die Nachricht KEINERLEI Bestellinfos enthält (z.B. nur 'Hallo' oder 'Was kostet das?').\n"
        "WICHTIG: extracted darf NUR Infos aus der NEUEN Nachricht enthalten!\n"
        "HALLUZINATION VERBOTEN: Erfinde NIEMALS Werte die der Kunde nicht gesagt hat!\n\n"
        "KRITISCHE BEISPIELE für Extraktion:\n"
        '- Berater fragt "Beschriftung?" + Kunde: "ja, Happy Birthday klingt gut" → intent=order, extracted={"beschriftung": "Happy Birthday"}\n'
        '- Berater fragt "Abholung oder Lieferung?" + Kunde: "ja ich will selber abholen" → intent=order, extracted={"abholung": "Abholung"}\n'
        '- Berater fragt "Allergien?" + Kunde: "nein hab keine" → intent=order, extracted={"allergien": "Keine"}\n'
        '- Berater fragt "Beschriftung?" + Kunde: "keine" → intent=order, extracted={"beschriftung": "Keine"}\n'
        '- Berater fragt "Beschriftung?" + Kunde: "ja, schreib Happy Birthday Max drauf" → intent=order, extracted={"beschriftung": "Happy Birthday Max"}\n'
        '- Kunde: "ich hole selbst ab" oder "selber abholen" → intent=change, extracted={"abholung": "Abholung"} (NICHT liefertermin!)\n'
        '- Kunde: "liefern bitte" oder "Lieferung" (OHNE Datum!) → intent=change, extracted={"abholung": "Lieferung"}\n'
        '- WICHTIG: "Lieferung am 28.03" oder "Lieferung am Samstag" = LIEFERTERMIN, NICHT Abholung ändern!\n'
        '  → intent=order, extracted={"liefertermin": "28.03.2026"} — abholung NICHT ändern!\n'
        '- "Liefertermin 31.03" oder "am 31. März" → intent=order, extracted={"liefertermin": "31.03.2026"}\n'
        '- Berater fragt "Abholung oder Lieferung?" + Kunde: "Abholung" → intent=order, extracted={"abholung": "Abholung"}\n'
        '- Berater fragt "Abholung oder Lieferung?" + Kunde: "Lieferung" → intent=order, extracted={"abholung": "Lieferung"}\n'
        "REGEL: Wenn der Kunde auf eine Berater-Frage antwortet (auch mit 'ja' + Inhalt oder einzelnem Wort), ist das IMMER intent=order!\n"
        "REGEL: 'abholen'/'hole ab'/'selbst abholen'/'Abholung' betrifft IMMER das Feld 'abholung', NIEMALS 'liefertermin'!\n"
        "REGEL: 'Lieferung am DATUM' oder 'Lieferung DATUM' → NUR liefertermin setzen! abholung NICHT ändern!\n"
        "REGEL: WENN abholung bereits im Gesprächsverlauf gesetzt wurde (z.B. 'Abholung'), "
        "DANN darf abholung NUR geändert werden wenn der Kunde EXPLIZIT sagt: 'doch liefern'/'ich will Lieferung statt Abholung'/'ändere zu Lieferung'. "
        "NIEMALS abholung ändern nur weil das Wort 'Lieferung' in einem Datum-Satz vorkommt!\n"
        "REGEL: Einzelne Wörter wie 'Abholung', 'Lieferung', 'Schokolade', 'Rund' als Antwort auf eine Frage → intent=order + korrekt extrahieren!"
    )

    history = format_history(state.get("messages", []))

    # ── HINT: Welches Feld wurde zuletzt gefragt? ──
    # Bug-Fix: Wenn Bot "Füllung?" fragt und User "Vanille" sagt,
    # ohne Hint denkt LLM oft "Vanille = Bestätigung Geschmack" und extrahiert nichts.
    # Mit Hint: "Antwort gehört zu fuellung" → korrekt zugeordnet.
    current_field = state.get("current_field", "")
    field_hint = ""
    if current_field:
        field_hint = (
            f"\n\n🎯 KRITISCHER HINWEIS: Der Berater hat ZULETZT nach dem Feld "
            f"'{current_field}' gefragt. Wenn die Kundennachricht eine plausible "
            f"Antwort darauf ist (z.B. einzelnes Wort, kurze Phrase), MUSST du sie "
            f"als '{current_field}' extrahieren — auch wenn derselbe Wert schon in "
            f"einem anderen Feld steht!\n"
            f"Beispiel: Bot fragt nach 'fuellung', User sagt 'Vanille', auch wenn "
            f"geschmack='Vanille' schon gesetzt ist → extracted={{'fuellung': 'Vanille'}}!"
        )

    messages = [
        {"role": "system", "content": combined_prompt + field_hint},
        {"role": "user", "content":
            f"Gesprächsverlauf:\n{history}\n\n"
            f"Neue Nachricht: {state['user_input']}"}
    ]

    raw = _llm_chat(messages, temperature=0, max_tokens=150)

    # JSON parsen
    def retry_call(retry_messages):
        return _llm_chat(retry_messages, temperature=0, max_tokens=150)

    try:
        result = parse_llm_json(
            raw, retry_func=retry_call, max_retries=1, context_messages=messages
        )
    except Exception:
        # Fallback: nur Intent parsen
        intent_raw = raw.strip().lower()
        result = {"intent": intent_raw, "extracted": {}}

    # Intent validieren
    intent = result.get("intent", "order").lower().strip()
    valid = ["greeting", "order", "price", "image", "info", "change", "finalize", "offtopic"]
    if intent not in valid:
        intent = "order"

    # GUARDRAIL: "ja"/"ok" nach "Preis berechnen?" → erzwinge price
    # Problem: LLM klassifiziert "ja" oft als "finalize" wenn order_complete=True,
    # auch wenn der Berater gerade nach Preis gefragt hat.
    if intent == "finalize":
        user_lower = state.get("user_input", "").lower().strip()
        simple_confirm = user_lower in (
            "ja", "ok", "klar", "bitte", "ja bitte", "ja gerne",
            "gerne", "ja natürlich", "ja, bitte", "ja, gerne"
        )
        if simple_confirm:
            last_bot_msg = ""
            for msg in reversed(state.get("messages", [])):
                if msg.get("role") == "assistant":
                    last_bot_msg = msg.get("content", "").lower()
                    break
            if "preis" in last_bot_msg and (
                "berechnen" in last_bot_msg or "aktualisiert" in last_bot_msg
                or "berechne" in last_bot_msg
            ):
                intent = "price"
                logger.info("Guardrail: 'ja' nach Preisfrage → intent=price (override von finalize)")

    state["intent"] = intent
    logger.info(f"Intent: {intent}")

    # Extrahierte Infos IMMER in order_info mergen — egal welcher Intent!
    # Wenn der Kunde "keine Allergien" sagt und der Intent "image" oder "finalize" ist,
    # dürfen wir die extrahierten Daten trotzdem nicht wegwerfen!
    extracted = result.get("extracted", {})
    if extracted:
        order_info = state.get("order_info", {})

        # SCHUTZ: "Lieferung am DATUM" darf abholung nicht überschreiben!
        # Fall 1: LLM hat beides extrahiert (liefertermin + abholung)
        # Fall 2: LLM hat nur abholung="Lieferung" extrahiert, aber die Nachricht
        #         enthält ein Datum → war ein Liefertermin, kein Abholungswechsel
        import re
        user_msg = state.get("user_input", "").lower().strip()
        has_date_pattern = bool(re.search(
            r'\d{1,2}[\./]\d{1,2}|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|morgen|übermorgen|nächst',
            user_msg
        ))

        if (extracted.get("abholung") and order_info.get("abholung")):
            # Fall 1: Beides extrahiert
            if extracted.get("liefertermin"):
                logger.info(
                    f"Schutz: 'abholung' nicht überschrieben (war '{order_info['abholung']}', "
                    f"LLM wollte '{extracted['abholung']}' wegen Liefertermin-Satz)"
                )
                del extracted["abholung"]
            # Fall 2: Nur abholung extrahiert, aber Nachricht enthält Datum
            # → LLM hat "Lieferung am DATUM" falsch als Abholungswechsel interpretiert
            elif has_date_pattern and "liefer" in user_msg:
                # Datum aus Nachricht extrahieren und als liefertermin setzen
                date_match = re.search(r'(\d{1,2}[\./]\d{1,2}(?:[\./]\d{2,4})?)', user_msg)
                if date_match:
                    extracted["liefertermin"] = date_match.group(1)
                logger.info(
                    f"Schutz: 'abholung' nicht überschrieben (war '{order_info['abholung']}', "
                    f"Nachricht enthält Datum → nur liefertermin='{extracted.get('liefertermin')}' gesetzt)"
                )
                del extracted["abholung"]

        for key, value in extracted.items():
            if isinstance(value, str) and value.strip():
                v = value.strip()
                # Dekoration: ersten Buchstaben großschreiben (verhindert "bräutigem" statt "Bräutigam")
                if key == "dekoration" and v and v[0].islower():
                    v = v[0].upper() + v[1:]
                order_info[key] = v
        state["order_info"] = order_info
        logger.info(f"Order Info (merged, intent={intent}): {order_info}")

    return state


# Rückwärtskompatibel: classify_intent als Alias
def classify_intent(state: AgentState) -> AgentState:
    return classify_and_extract(state)


# ═══════════════════════════════════════
# NODE 2: GREET
# ═══════════════════════════════════════
@trace_node("greet")
@safe_node()
def greet(state: AgentState) -> AgentState:
    """Begrüßt den Kunden freundlich und fragt direkt nach dem Anlass."""
    config = load_prompts_config()
    first_question = config.get("field_questions", {}).get("anlass", "Was für eine Torte darf es sein?")
    state["response"] = (
        f"{config['prompts']['greet']} "
        f"{first_question}"
    )
    return state


# ═══════════════════════════════════════
# NODE 3: EXTRACT INFO
# ═══════════════════════════════════════
@trace_node("extract_info")
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
@trace_node("check_complete")
@safe_node()
def check_complete(state: AgentState) -> AgentState:
    """Prüft welche Bestellinfos noch fehlen. Filtert vage Werte raus."""

    # Vage Werte zählen nicht als "ausgefüllt"
    vague_values = {"ja", "nein", "eine", "ein", "deko", "dekoration", "auch",
                    "mit deko", "mit dekoration", "ok", "klar"}

    required = get_required_fields()
    order_info = state.get("order_info", {})

    missing = []
    for f in required:
        val = order_info.get(f, "")
        if not val or (isinstance(val, str) and val.lower().strip() in vague_values):
            missing.append(f)
            # Vagen Wert entfernen damit ask_next nochmal fragt
            if f in order_info and isinstance(val, str) and val.lower().strip() in vague_values:
                del order_info[f]

    state["order_info"] = order_info
    state["missing_fields"] = missing
    state["order_complete"] = len(missing) == 0

    # ── TODO-Liste synchronisieren ──
    # "answered" wenn Feld ausgefüllt, "asked"/"pending" bleibt bestehen solange leer
    question_todo = state.get("question_todo", {})
    for f in required:
        if f not in question_todo:
            question_todo[f] = "pending"
        if f not in missing:
            # Feld ist befüllt → als beantwortet markieren
            question_todo[f] = "answered"
        # Feld fehlt noch: Status "asked" oder "pending" bleibt wie er ist

    # Optionale Felder auch synchronisieren (wichtig für Kalender-Widget!)
    for opt_field in ["liefertermin", "lieferadresse", "farbe"]:
        if order_info.get(opt_field):
            question_todo[opt_field] = "answered"

    state["question_todo"] = question_todo

    logger.info(f"Complete: {state['order_complete']} | Missing: {missing}")
    logger.debug(f"TODO: {question_todo}")
    return state


# ═══════════════════════════════════════
# NODE 5: ASK NEXT QUESTION
# ═══════════════════════════════════════
@trace_node("ask_next")
@safe_node(fallback_response="Was möchten Sie mir noch zu Ihrem Kuchen erzählen?")
def ask_next(state: AgentState) -> AgentState:
    """
    Fragt nach der nächsten fehlenden Info.
    Nutzt die TODO-Liste: Bevorzugt Felder die schon gefragt wurden (asked)
    vor neuen Feldern (pending). Markiert das gefragte Feld als 'asked'.

    PERFORMANCE-FIX (Plan B): Kein LLM-Call mehr — Frage kommt direkt aus
    `field_questions` in prompts_config.yaml. Spart 1 OpenAI-Request pro Turn.
    Trade-off: weniger Smalltalk-Variation (immer dieselbe Frage pro Feld).
    Vorher mussten 3 LLM-Calls pro Turn warten (= bei 5 RPM nach 2 Nachrichten
    schon Rate-Limit). Mit Plan B ist es nur noch 1 Call → 3× mehr Turns/min.
    """

    field_questions = get_field_questions()

    missing = state.get("missing_fields", [])
    order_info = state.get("order_info", {})
    question_todo = state.get("question_todo", {})

    if not missing:
        # Sollte nicht passieren wenn graph richtig routet — aber sicher ist sicher
        state["response"] = "Was möchten Sie mir noch zu Ihrem Kuchen erzählen?"
        state["current_field"] = ""
        return state

    # ── Reihenfolge: erst "asked" (warten auf Antwort), dann "pending" (neu) ──
    asked_fields = [f for f in missing if question_todo.get(f) == "asked"]
    pending_fields = [f for f in missing if question_todo.get(f) != "asked"]
    ordered_missing = asked_fields + pending_fields

    # Nächstes Feld in der Priorität auswählen
    next_field = ordered_missing[0] if ordered_missing else missing[0]
    question = field_questions.get(next_field, f"Was wünschen Sie sich für {next_field}?")

    # ── Optional: kleiner Smalltalk-Vorspann, deterministisch ──
    prefix = ""
    person = order_info.get("person", "")
    last_input = (state.get("user_input", "") or "").strip().lower()

    # Nach kurzer Kundenantwort einmal bestätigen
    if last_input and len(last_input) <= 30 and asked_fields:
        # Kunde hat gerade auf eine vorherige Frage geantwortet
        prefix = "Super, danke! "
    elif person and next_field == "anlass":
        prefix = f"Schön, dass es um {person} geht! "

    state["response"] = f"{prefix}{question}"

    # ── TODO aktualisieren: gefragtes Feld auf "asked" setzen ──
    if next_field in question_todo and question_todo[next_field] != "answered":
        question_todo[next_field] = "asked"
        state["question_todo"] = question_todo
        logger.info(f"TODO (deterministic): '{next_field}' → asked")

    # Aktuell gefragtes Feld im State merken (für Frontend-Buttons)
    state["current_field"] = next_field

    return state


# ═══════════════════════════════════════
# NODE 6: SUMMARIZE ORDER
# ═══════════════════════════════════════
@trace_node("summarize_order")
@safe_node()
def summarize_order(state: AgentState) -> AgentState:
    """Fasst die komplette Bestellung zusammen wenn alle Infos da sind."""

    order_info = state.get("order_info", {})

    labels = {
        "anlass": "Anlass", "gaeste": "Für", "geschmack": "Kuchen",
        "form": "Form", "schichten": "Schichten", "fuellung": "Füllung",
        "dekoration": "Dekoration", "farbe": "Farbe",
        "allergien": "Allergien", "beschriftung": "Beschriftung",
        "abholung": "Abholung",
        "lieferadresse": "Lieferadresse", "liefertermin": "Liefertermin"
    }

    summary_parts = []
    for key, label in labels.items():
        if order_info.get(key):
            summary_parts.append(f"{label}: {order_info[key]}")

    summary = ", ".join(summary_parts)

    state["response"] = (
        f"Ihre Bestellung ist komplett! Hier die Zusammenfassung: {summary}. "
        f"Ich generiere jetzt Ihr Vorschaubild... 🎨"
    )
    return state


# ═══════════════════════════════════════
# NODE 7: RETRIEVE DOCS (RAG)
# ═══════════════════════════════════════
@trace_node("retrieve_docs")
@safe_node(fallback_response="Ich konnte leider keine Informationen abrufen.")
def retrieve_docs(state: AgentState) -> AgentState:
    """Sucht relevante Dokumenten-Chunks in ChromaDB."""

    # Bei Preis-Intent: Bestelldetails als Query (nicht den vagen User-Input)
    intent = state.get("intent", "")
    order_info = state.get("order_info", {})
    if intent == "price" and order_info:
        query_parts = [f"{k}: {v}" for k, v in order_info.items() if v]
        query = "Preis Kuchen " + ", ".join(query_parts)
    else:
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
@trace_node("calculate_price")
@safe_node(fallback_response="Ich konnte den Preis leider nicht berechnen. Rufen Sie uns an unter 0221-1234567.")
def calculate_price(state: AgentState) -> AgentState:
    """Berechnet den Preis basierend auf Bestellinfos + Dokument-Kontext."""

    config = load_prompts_config()
    system_prompt = config["prompts"]["calculate_price"]
    order_info = state.get("order_info", {})
    context = state.get("context", "")
    history = format_history(state.get("messages", [])[-6:])

    # Abholung/Lieferung explizit klären — LLM ignoriert sonst die Regel
    abholung_val = (order_info.get("abholung") or "").lower().strip()
    is_pickup = abholung_val in ("abholung", "selbst abholen", "abholen", "selbstabholung")

    if is_pickup:
        lieferhinweis = (
            "\n\nWICHTIG: Der Kunde holt SELBST AB (Abholung)! "
            "Es dürfen KEINE Lieferkosten berechnet werden! "
            "KEINE Zeile mit 'Lieferung' in der Tabelle!"
        )
    else:
        lieferhinweis = (
            "\n\nHINWEIS: Der Kunde möchte Lieferung. "
            "Lieferkosten hinzufügen: Köln = +10 €, Umkreis = +20 €."
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content":
            f"KONTEXT (Preisliste):\n{context}\n\n"
            f"BESTELLDETAILS:\n{json.dumps(order_info, ensure_ascii=False)}\n\n"
            f"GESPRÄCHSVERLAUF:\n{history}\n\n"
            f"Berechne den Gesamtpreis.{lieferhinweis}"}
    ]

    response_text = _llm_chat(messages, temperature=0, max_tokens=600)

    # Bereinigung: LLM schreibt manchmal "210 €/Person" oder "€/" → nur "210 €" behalten
    import re as _re_clean
    response_text = _re_clean.sub(r'(\d+)\s*€\s*/\w*', r'\1 €', response_text)
    # Bereinigung: Tabelleninhalt mit "/" ohne Preis ("€/") entfernen
    response_text = _re_clean.sub(r'€/', '€', response_text)

    # Nachbearbeitung: Falls LLM trotzdem Lieferung bei Abholung berechnet → entfernen
    if is_pickup and "Lieferung" in response_text:
        import re as _re2
        # Zeile mit Lieferung aus der HTML-Tabelle entfernen
        response_text = _re2.sub(
            r'<tr>\s*<td>[^<]*Lieferung[^<]*</td>\s*<td>[^<]*</td>\s*</tr>',
            '', response_text, flags=_re2.IGNORECASE
        )
        # Gesamtpreis neu berechnen: Alle Preise aus Tabelle summieren
        preise = _re2.findall(r'<td>(\d+)\s*€</td>', response_text)
        if preise:
            total = sum(int(p) for p in preise)
            response_text = _re2.sub(
                r'(<tr class=["\']total-row["\']>.*?<b>)\s*\d+\s*€',
                f'\\g<1>{total} €',
                response_text, flags=_re2.DOTALL
            )
        logger.info("Lieferkosten bei Abholung entfernt (Post-Processing)")

    state["response"] = response_text

    # ── Gesamtpreis aus HTML-Tabelle extrahieren und im State speichern ──
    # Damit das PDF denselben Preis wie die Chat-Tabelle zeigt
    import re as _re
    price_match = _re.search(
        r'class=["\']total-row["\'].*?<b>\s*(\d+[\d.,]*)\s*€',
        response_text, _re.DOTALL
    )
    if price_match:
        state["calculated_price"] = f"{price_match.group(1)} €"
        logger.info(f"Preis aus Chat-Tabelle extrahiert: {state['calculated_price']}")

    return state


# ═══════════════════════════════════════
# NODE 9: ANSWER QUESTION (Info)
# ═══════════════════════════════════════
@trace_node("answer_question")
@safe_node(fallback_response="Dazu kann ich leider keine Auskunft geben. Rufen Sie uns an unter 0221-1234567.")
def answer_question(state: AgentState) -> AgentState:
    """Beantwortet allgemeine Fragen basierend auf RAG-Kontext."""

    config = load_prompts_config()
    system_prompt = config["prompts"]["answer_question"]
    context = state.get("context", "")
    question = state.get("user_input", "")
    history = format_history(state.get("messages", [])[-6:])

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content":
            f"KONTEXT:\n{context}\n\n"
            f"GESPRÄCHSVERLAUF:\n{history}\n\n"
            f"FRAGE: {question}"}
    ]

    state["response"] = _llm_chat(messages, temperature=0.3, max_tokens=200)
    return state


# ═══════════════════════════════════════
# NODE 10: GENERATE IMAGE
# ═══════════════════════════════════════
# ═══════════════════════════════════════
# BILD-PROVIDER: OpenAI → HuggingFace (Fallback-Kette)
# ═══════════════════════════════════════

def _save_image_bytes(image_bytes: bytes, label: str) -> str:
    """Speichert Bild-Bytes als PNG-Datei und gibt den URL-Pfad zurück."""
    fname = f"{uuid.uuid4().hex}.png"
    fpath = f"static/images/{fname}"
    with open(fpath, "wb") as f:
        f.write(image_bytes)
    logger.info(f"Bild gespeichert ({label}): {fpath} ({len(image_bytes)} bytes)")
    return f"/static/images/{fname}"


def _generate_openai(prompt: str, label: str) -> str:
    """Versucht Bildgenerierung über OpenAI API (gpt-image-1 / dall-e-3)."""
    model = IMAGE_MODEL
    kwargs = {"model": model, "prompt": prompt, "n": 1}

    if "gpt-image-1" in model:
        # gpt-image-1 gibt Base64-Daten zurück, output_format ist das Bildformat
        kwargs["size"] = "1024x1024"
        kwargs["output_format"] = "png"
    elif model == "dall-e-3":
        kwargs["size"] = "1024x1024"
        kwargs["quality"] = "standard"
        kwargs["response_format"] = "b64_json"
    else:
        kwargs["size"] = "1024x1024"

    logger.info(f"OpenAI Bild-Request: model={model}, prompt_len={len(prompt)}")
    import time as _t
    _t0 = _t.time()
    resp = openai_image_client.images.generate(**kwargs)
    _dur = (_t.time() - _t0) * 1000
    item = resp.data[0]

    # gpt-image-1 gibt b64_json zurück, dall-e-3 kann url oder b64_json geben
    b64_data = getattr(item, "b64_json", None) or getattr(item, "b64", None)
    if b64_data:
        url = _save_image_bytes(base64.b64decode(b64_data), label)
        trace_image_gen(prompt[:300], "openai", image_url=url, duration_ms=_dur)
        return url
    elif getattr(item, "url", None):
        import urllib.request
        fname = f"{uuid.uuid4().hex}.png"
        fpath = f"static/images/{fname}"
        urllib.request.urlretrieve(item.url, fpath)
        logger.info(f"Bild generiert via OpenAI ({label}): {fpath}")
        return f"/static/images/{fname}"
    # Debug: Was hat die API zurückgegeben?
    logger.error(f"OpenAI Antwort unbekanntes Format: {dir(item)} | {item}")
    raise RuntimeError("Kein Bild in OpenAI-Antwort")


def _hf_post(url: str, payload: dict, timeout: int = 120) -> requests.Response:
    """Hilfsfunktion: POST zu HuggingFace Inference API."""
    return requests.post(
        url,
        headers={"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"},
        json=payload,
        timeout=timeout,
    )


def _generate_huggingface(prompt: str, label: str, seed: int = None) -> str:
    """Bildgenerierung über HuggingFace Inference API.
    Primär: FLUX.1-schnell (kein Collage-Problem, folgt Anweisungen gut)
    Fallback: SDXL"""
    if not HUGGINGFACE_API_KEY:
        raise RuntimeError("Kein HUGGINGFACE_API_KEY konfiguriert")

    # FLUX braucht einen klaren, beschreibenden Prompt
    flux_prompt = (
        "A single professional food photograph of ONE custom birthday cake. "
        + prompt
        + " One cake only, centered on clean white background, soft studio lighting, "
        "photorealistic, high-end bakery quality."
    )

    # ── Versuch 1: FLUX.1-schnell (kein Collage-Problem, besser als SDXL) ──
    flux_url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    flux_payload = {"inputs": flux_prompt}
    if seed is not None:
        flux_payload["parameters"] = {"seed": seed}

    try:
        logger.info(f"FLUX Prompt: {flux_prompt[:100]}...")
        resp = _hf_post(flux_url, flux_payload)
        if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
            logger.info(f"Bild generiert via FLUX.1-schnell ({label})")
            url = _save_image_bytes(resp.content, label)
            trace_image_gen(prompt[:300], "flux", image_url=url)
            return url
        if resp.status_code == 503:
            import time
            wait = min(resp.json().get("estimated_time", 20), 40)
            logger.info(f"FLUX lädt, warte {wait}s...")
            time.sleep(wait)
            resp = _hf_post(flux_url, flux_payload)
            if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
                url = _save_image_bytes(resp.content, label)
                trace_image_gen(prompt[:300], "flux", image_url=url)
                return url
        # Detailliertes Error-Logging
        try:
            err_body = resp.text[:300]
        except Exception:
            err_body = "(kein Body)"
        logger.warning(f"FLUX fehlgeschlagen: HTTP {resp.status_code} | {err_body}")
    except Exception as e:
        logger.warning(f"FLUX Exception: {type(e).__name__}: {e}")

    # ── Versuch 2: SDXL (Fallback, neigt zu Collagen aber funktioniert meistens) ──
    sdxl_prompt = (
        "Single photograph of ONE cake only, centered composition. "
        + prompt
        + " No collage, no grid, no multiple images. One single cake."
    )
    sdxl_url = "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0"
    sdxl_payload = {
        "inputs": sdxl_prompt,
        "parameters": {
            "negative_prompt": "collage, multiple images, grid, split screen, mosaic, "
                               "multiple cakes, text, watermark, blurry, low quality, "
                               "pattern, repeating, tiled",
        },
    }
    if seed is not None:
        sdxl_payload["parameters"]["seed"] = seed

    resp = _hf_post(sdxl_url, sdxl_payload)
    if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
        url = _save_image_bytes(resp.content, label)
        trace_image_gen(prompt[:300], "sdxl", image_url=url)
        return url

    if resp.status_code == 503:
        import time
        wait = min(resp.json().get("estimated_time", 30), 60)
        logger.info(f"SDXL lädt, warte {wait}s...")
        time.sleep(wait)
        resp = _hf_post(sdxl_url, sdxl_payload)
        if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
            url = _save_image_bytes(resp.content, label)
            trace_image_gen(prompt[:300], "sdxl", image_url=url)
            return url

    try:
        err_body = resp.text[:300]
    except Exception:
        err_body = "(kein Body)"
    logger.error(f"SDXL auch fehlgeschlagen: HTTP {resp.status_code} | {err_body}")
    raise RuntimeError(f"HuggingFace Fehler {resp.status_code}: {err_body}")


# Cache: wenn OpenAI einmal 403 gibt, nicht mehr versuchen (bis Server-Neustart)
_openai_image_blocked = False


def _build_llm_image_prompt(order_info: dict, sanitize_names: bool = True) -> str | None:
    """Generiert einen Bild-Prompt der den Kundenwunsch so genau wie möglich umsetzt.
    sanitize_names=True: für OpenAI (ersetzt echte Namen)
    sanitize_names=False: für HuggingFace (behält Namen bei)"""

    deko = order_info.get("dekoration", "")
    farbe = order_info.get("farbe", "")
    anlass = order_info.get("anlass", "")
    geschmack = order_info.get("geschmack", "")
    form = order_info.get("form", "")
    schichten = order_info.get("schichten", "")
    fuellung = order_info.get("fuellung", "")
    beschriftung = order_info.get("beschriftung", "")

    # Kundenbeschreibung — DEKORATION ZUERST (wichtigstes Element)
    kunde_details = []
    if deko:        kunde_details.append(f"WICHTIGSTE DEKORATION: {deko}")
    if farbe:       kunde_details.append(f"Fondant-Farbe: {farbe}")
    if anlass:      kunde_details.append(f"Anlass: {anlass}")
    if geschmack:   kunde_details.append(f"Geschmack: {geschmack}")
    if form:        kunde_details.append(f"Form: {form}")
    # Schichten mit expliziten Farben für den LLM-Prompt
    import re as _re
    _layer_colors = {
        "schoko": "dark brown", "schokolade": "dark brown", "chocolate": "dark brown",
        "vanille": "light cream/white", "vanilla": "light cream/white", "vanile": "light cream/white",
        "erdbeer": "pink", "erdbeere": "pink", "strawberry": "pink",
        "zitrone": "bright yellow", "lemon": "bright yellow",
        "himbeere": "deep red", "karamell": "golden caramel",
        "beeren": "dark purple",
    }
    n_layers = int(_re.findall(r'\d+', str(schichten))[0]) if _re.findall(r'\d+', str(schichten)) else 0
    # Füllung-Parsing: "erdbeer und schoko" → ["erdbeer", "schoko"]
    _fp_clean = fuellung.replace(".", ":").replace("+", ",") if fuellung else ""
    _fp_clean = _re.sub(r'\s+und\s+', ',', _fp_clean, flags=_re.IGNORECASE)
    _fp_clean = _re.sub(r'\s+and\s+', ',', _fp_clean, flags=_re.IGNORECASE)
    _fp = [f.strip() for f in _re.split(r'[,:]', _fp_clean) if f.strip() and not f.strip().isdigit()] if _fp_clean else []

    # ── Tier-Beschreibung: feuert ab 2 Etagen (vorher erst ab 3!) ──
    # Bug-Fix: User bestellt "Schichten: 2" → Modell ignorierte schwaches "Schichten: 2"
    # und machte 1 Etage. Jetzt: explizite "EXACTLY N tiers" Anweisung ab 2.
    if n_layers >= 2:
        # Füllungen auf n_layers auffüllen — bei zu wenigen: letzten wiederholen oder geschmack nutzen
        _fp_filled = list(_fp) if _fp else []
        while len(_fp_filled) < n_layers:
            # Fallback: geschmack als Standardfüllung, sonst letzte Füllung wiederholen
            fallback = geschmack if geschmack else (_fp_filled[-1] if _fp_filled else "vanilla")
            _fp_filled.append(fallback)

        layer_list = []
        if n_layers == 2:
            positions = ["bottom", "top"]
        elif n_layers == 3:
            positions = ["bottom", "middle", "top"]
        else:
            positions = ["bottom"] + [f"layer {i+1}" for i in range(1, n_layers - 1)] + ["top"]

        for i, part in enumerate(_fp_filled[:n_layers]):
            pos = positions[i] if i < len(positions) else f"layer {i+1}"
            color = _layer_colors.get(part.lower(), part)
            layer_list.append(f"{pos}: {color} {part}")

        n_words = {2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE"}.get(n_layers, str(n_layers))
        kunde_details.append(
            f"FONDANT-ETAGEN (KRITISCH - EXACTLY {n_words} ({n_layers}) übereinander gestapelte "
            f"Fondant-Etagen, jede eine ANDERE FARBE, von AUSSEN sichtbar! "
            f"NICHT eine einzelne Etage mit Schichten innendrin!): {', '.join(layer_list)}"
        )
    else:
        if schichten: kunde_details.append(f"Schichten: {schichten}")
        if fuellung:  kunde_details.append(f"Füllung: {fuellung}")

    # Beschriftung NICHT im Bild-Prompt (FLUX rendert Text schlecht)
    # Wird nur in der Bestellung gespeichert

    info_str = "\n".join(kunde_details) if kunde_details else "Schöner Geburtstagskuchen"

    name_rule = (
        "2. Ersetze NUR echte Personennamen durch visuelle Rollenbeschreibung:\n"
        "   'Ronaldo' → 'famous soccer player figurine with short dark hair'\n"
        "   'Elsa' → 'ice queen princess with platinum blonde braid'\n"
        "   'Mickey Mouse' → 'classic cartoon mouse with large round ears'\n"
        "   'Braut und Bräutigam' / 'Avatar Braut Bräutigam' → "
        "'elegant bride fondant figurine in white dress and groom fondant figurine in dark suit standing together on top tier'\n"
        "   'Braut' allein → 'elegant bride fondant figurine in long white wedding dress'\n"
        "   'Bräutigam' allein → 'groom fondant figurine in dark suit with bow tie'\n"
        "3. WICHTIG für Moderation-Sicherheit: Ersetze IMMER Beschreibungen von Kindern/Menschen:\n"
        "   'ein Junge' → 'a small cartoon boy figurine'\n"
        "   'ein Mädchen' → 'a small cartoon girl figurine'\n"
        "   'Kind/Kinder' → 'small cartoon figurine(s)'\n"
        "   'Baby' → 'cute cartoon baby figurine'\n"
        "   Beschreibe Personen-Figuren IMMER als 'cartoon figurine' oder 'fondant figurine'!\n"
    ) if sanitize_names else (
        "2. Behalte ALLE Namen exakt bei (Ronaldo, Messi, Elsa, Mickey Mouse etc.)\n"
    )

    try:
        prompt = _llm_chat([
            {"role": "system", "content":
                "Du bist ein Experte für Bild-Prompts für Kuchenfotografie.\n"
                "AUFGABE: Erstelle einen englischen Bildprompt.\n\n"
                "KRITISCH WICHTIG — REIHENFOLGE IM PROMPT:\n"
                "1. ZUERST die Fondant-Etagen beschreiben (WICHTIGSTES ELEMENT!)\n"
                "2. DANN die Dekoration auf der obersten Etage\n"
                "3. DANN Hintergrund/Beleuchtung\n\n"
                "REGELN:\n"
                "1. FONDANT-ETAGEN sind das HAUPTELEMENT! Der Kuchen MUSS mehrere übereinander gestapelte "
                "Fondant-Etagen (tiers) haben, JEDE Etage eine ANDERE FARBE, von AUSSEN sichtbar! "
                "Der Kuchen MUSS einen sauberen keilförmigen Anschnitt haben, der die inneren Schichten zeigt!\n"
                f"{name_rule}"
                "3. FORM DES KUCHENS — KRITISCH:\n"
                "   - 'Herzform'/'Herz' → 'heart-shaped cake' (NICHT rund!)\n"
                "   - 'eckig'/'quadratisch' → 'square-shaped cake' (NICHT rund!)\n"
                "   - 'rund' oder keine Angabe → 'round cake'\n"
                "   Die Form MUSS im ERSTEN Satz des Prompts stehen! z.B. 'heart-shaped tiered cake'\n"
                "4. Szenen EXAKT beibehalten: Fussballfeld → grünes Fondant-Fussballfeld mit weißen Linien AUF der obersten Etage\n"
                "5. Jede Etage mit 'smooth [farbe] fondant' beschreiben\n"
                "6. ETAGEN SIND KRITISCH: Jede Etage EINZELN mit Position und Farbe auflisten! "
                "Format: 'bottom tier: smooth [color] fondant, top tier: smooth [color] fondant'. "
                "JEDE Etage muss eine KOMPLETT ANDERE Farbe haben und von AUSSEN klar erkennbar sein! "
                "Dünne Creme-Linie zwischen den Etagen. "
                "Bei N=2: Es MÜSSEN ZWEI separate, übereinander gestapelte Etagen sein — NICHT eine "
                "einzelne Etage mit horizontalen Schichten innen! Die Etagen müssen von außen als zwei "
                "Stockwerke sichtbar sein.\n"
                "Beispiel für 2 Etagen mit schoko + vanille: "
                "'two-tier cake with EXACTLY TWO separate fondant-covered tiers stacked on top of each other: "
                "bottom tier smooth dark brown chocolate fondant, top tier smooth cream white vanilla fondant. "
                "Two clearly distinct tiers as two separate stacked stories with a thin cream line between them.'\n"
                "Beispiel für 3 Etagen mit schoko+vanille+zitrone: "
                "'very tall tiered cake with EXACTLY THREE separate fondant-covered tiers stacked on top of each other: "
                "bottom tier smooth dark brown chocolate fondant, middle tier smooth cream white vanilla fondant, "
                "top tier smooth bright yellow lemon fondant. Each tier a clearly different color, thin cream line between tiers.'\n"
                "7. NIEMALS Text, Buchstaben oder Beschriftung auf dem Kuchen zeigen! Kein Text im Bild!\n"
                "8. IMMER: ein Kuchen, weißer Hintergrund, Studiolicht, photorealistisch\n"
                "9. Max 100 Wörter, NUR den englischen Prompt, keine Anführungszeichen\n\n"
                "BEISPIEL:\n"
                "Kunde: 'DEKORATION: Fussballspieler auf Fussballfeld, Form: Herzform, Farbe: rot, Schichten: 3, "
                "Füllung: schoko+vanille+erdbeer, Geschmack: schoko'\n"
                "→ 'Professional bakery photo of a VERY TALL heart-shaped tiered birthday cake with EXACTLY THREE "
                "separate fondant-covered tiers stacked on top of each other: bottom tier smooth dark brown "
                "chocolate fondant, middle tier smooth cream white vanilla fondant, top tier smooth pink "
                "strawberry fondant. Each tier a completely different color with thin cream line between them. "
                "The cake has a clean wedge-shaped slice cut out, revealing the distinct internal layers "
                "of chocolate, vanilla and strawberry sponge with cream filling between them. "
                "The top tier is decorated as a miniature green football field with white line markings, "
                "with a fondant soccer player figurine in red jersey. "
                "Clean white background, soft studio lighting, photorealistic, appetizing.'"},
            {"role": "user", "content": f"Kundenwunsch:\n{info_str}"}
        ], temperature=0, max_tokens=200)
        result = prompt.strip().strip('"').strip("'")
        logger.info(f"LLM-Bildprompt ({'OpenAI' if sanitize_names else 'HuggingFace'}): {result}")
        return result
    except Exception as e:
        logger.warning(f"LLM-Bildprompt-Generierung fehlgeschlagen: {e}")
        return None


_ULTRA_SAFE_PROMPT = (
    "Professional food photography, single custom celebration cake with THREE fondant-covered tiers "
    "stacked on top of each other: bottom tier smooth pink fondant, middle tier smooth white fondant, "
    "top tier smooth light blue fondant. Each tier a different color, thin cream line between tiers. "
    "Elegant sugar flowers decoration on top tier. "
    "Clean white background, soft studio lighting, high-end bakery quality, photorealistic, appetizing."
)


def _deko_has_person_name(deko: str) -> bool:
    """Erkennt ob die Dekoration einen echten Personennamen enthält
    (Sportler, Schauspieler, Zeichentrickfiguren mit Copyright).
    Diese Prompts werden von OpenAI geblockt → direkt zu HuggingFace."""
    if not deko:
        return False
    # Bekannte Namen die OpenAI-Moderation triggern (inkl. deutsche Schreibweisen)
    known_names = [
        # Sportler
        "ronaldo", "messi", "neymar", "mbappe", "mbappé", "lewandowski", "benzema",
        "beckham", "zidane", "maradona", "pele", "pelé", "haaland", "salah",
        "müller", "özil", "kroos", "neuer",
        # Disney / Zeichentrick (EN + DE)
        "mickey", "micky", "mickymaus", "micky maus", "mickey mouse",
        "minnie", "donald duck", "goofy", "simba", "nemo", "dory",
        "elsa", "anna", "moana", "rapunzel", "ariel", "cinderella", "aschenputtel",
        "winnie", "winnie puuh", "winnie pooh",
        "frozen", "eiskönigin",
        # Superhelden
        "spiderman", "spider-man", "spider man",
        "batman", "superman", "iron man", "hulk", "thor", "deadpool",
        "captain america", "wonder woman",
        # Andere Figuren
        "harry potter", "hermione", "mario", "luigi", "pikachu", "pokemon",
        "peppa", "paw patrol", "bluey", "encanto", "mirabel",
        "spongebob", "schwammkopf", "bob der baumeister", "bob the builder",
        "barbie", "transformer", "ninja turtle",
        "mascha", "olaf", "cars", "mcqueen", "lightning mcqueen",
        "rotkäppchen", "rotkaeppchen",
        # Musiker
        "taylor swift", "beyonce", "drake", "eminem",
    ]
    deko_lower = deko.lower()
    return any(name in deko_lower for name in known_names)


def generate_single_image(prompt: str, label: str, seed: int = None, order_info: dict = None) -> str:
    """
    Generiert EIN Bild mit Provider-Routing:
    1. OpenAI IMMER zuerst (prompt wird direkt genutzt — KEIN extra LLM-Call!)
    2. HuggingFace als Fallback
    Der übergebene prompt enthält bereits ALLES (Anschnitt, Referenz, Farben etc.)
    """
    global _openai_image_blocked

    deko = (order_info or {}).get("dekoration", "")
    has_person = _deko_has_person_name(deko)

    # Der combined_prompt von generate_image() ist bereits komplett —
    # KEIN zusätzlicher _build_llm_image_prompt() Call nötig!
    # Nur bei Personennamen: Namen sanitizen für OpenAI
    openai_prompt = prompt
    hf_prompt = prompt

    # ── Kinder/Personen-Wörter sanitizen (OpenAI Moderation) ──
    import re as _re
    _child_replacements = {
        r'\ba boy\b': 'a small cartoon boy figurine',
        r'\bgirl\b': 'cartoon girl figurine',
        r'\bchild\b': 'cartoon figurine',
        r'\bchildren\b': 'cartoon figurines',
        r'\bbaby\b': 'cute cartoon baby figurine',
        r'\bkid\b': 'cartoon figurine',
        r'\bkids\b': 'cartoon figurines',
        r'\byoung boy\b': 'small cartoon boy figurine',
        r'\byoung girl\b': 'small cartoon girl figurine',
        r'\blittle boy\b': 'small cartoon boy figurine',
        r'\blittle girl\b': 'small cartoon girl figurine',
    }
    for pattern, repl in _child_replacements.items():
        openai_prompt = _re.sub(pattern, repl, openai_prompt, flags=_re.IGNORECASE)

    if has_person:
        # Für OpenAI: Personennamen durch Beschreibung ersetzen
        _name_replacements = {
            "ronaldo": "famous soccer player figurine with short dark hair and athletic build",
            "messi": "famous soccer player figurine with beard and short hair",
            "neymar": "soccer player figurine with styled hair",
            "mbappe": "young soccer player figurine",
            "haaland": "tall blonde soccer player figurine",
            "elsa": "ice queen princess figurine with platinum blonde braid and blue dress",
            "anna": "princess figurine with auburn braids and green dress",
            "moana": "polynesian princess figurine with long dark hair",
            "rapunzel": "princess figurine with very long golden hair",
            "ariel": "mermaid princess figurine with red hair",
            "cinderella": "princess figurine in blue ball gown",
            "spiderman": "red and blue superhero figurine with web pattern",
            "spider-man": "red and blue superhero figurine with web pattern",
            "batman": "dark superhero figurine with cape and mask",
            "superman": "superhero figurine with red cape and S symbol",
            "iron man": "red and gold armored superhero figurine",
            "hulk": "large green superhero figurine",
            "mickey mouse": "classic cartoon mouse figurine with large round ears and red shorts",
            "mickey": "classic cartoon mouse figurine with large round ears",
            "minnie": "cartoon mouse figurine with polka dot bow",
            "paw patrol": "cartoon rescue puppy figurines",
            "peppa": "cartoon pink pig figurine",
            "frozen": "ice queen themed winter decoration",
            "mario": "cartoon plumber figurine with red cap and mustache",
            "pikachu": "yellow electric cartoon creature figurine",
            "barbie": "fashion doll figurine with pink outfit",
            "spongebob": "yellow square cartoon character figurine",
        }
        sanitized = prompt
        for name, replacement in _name_replacements.items():
            sanitized = _re.sub(
                rf'\b{_re.escape(name)}\b',
                replacement,
                sanitized,
                flags=_re.IGNORECASE
            )
        openai_prompt = sanitized
        logger.info(f"Bildgenerierung ({label}): Personenname erkannt → OpenAI mit sanitized names")

    # ── 1. OpenAI IMMER zuerst ──
    if not _openai_image_blocked:
        try:
            logger.info(f"Bildgenerierung ({label}): OpenAI {IMAGE_MODEL}")
            logger.info(f"Prompt ({len(openai_prompt)} chars): {openai_prompt[:400]}...")
            return _generate_openai(openai_prompt, label)
        except Exception as e:
            err_str = str(e).lower()
            logger.error(f"OpenAI Bild-FEHLER ({label}): {type(e).__name__}: {e}")
            if "403" in str(e) or "model_not_found" in err_str or "does not have access" in err_str:
                _openai_image_blocked = True
                logger.warning("OpenAI Bildmodell nicht verfügbar → Fallback HuggingFace")
            elif "429" in str(e) or "rate_limit" in err_str:
                logger.warning(f"OpenAI Rate Limit ({label}) → warte 15s und retry")
                import time
                time.sleep(15)
                try:
                    return _generate_openai(openai_prompt, label)
                except Exception as e2:
                    logger.error(f"OpenAI Retry auch fehlgeschlagen: {e2}")
            elif "moderation" in err_str or "safety" in err_str:
                logger.warning(f"OpenAI Moderation-Block ({label}) → Fallback HuggingFace")

    # ── 2. HuggingFace Fallback ──
    try:
        if getattr(generate_single_image, '_hf_exhausted', False):
            logger.warning("HuggingFace Credits aufgebraucht — überspringe")
            raise RuntimeError("HuggingFace Credits aufgebraucht (402)")
        logger.info(f"Bildgenerierung ({label}): HuggingFace FLUX/SDXL (Fallback)")
        return _generate_huggingface(hf_prompt, label, seed=seed)
    except Exception as e:
        if "402" in str(e):
            generate_single_image._hf_exhausted = True
        logger.error(f"HuggingFace fehlgeschlagen ({label}): {type(e).__name__}: {e}")
        raise RuntimeError(f"Alle Provider fehlgeschlagen ({label})")


# ═══════════════════════════════════════
# REFERENZBILD-SUCHE (Schnelles Dateiname-Matching)
# ═══════════════════════════════════════
# Dateiname-Konvention: avatar_Netagen.png
# z.B. elsa_3_etagen.png, ronaldo_2_etagen.png, batman_3_etagen.png

# Cache für Dateiliste
_reference_cache: dict = {"files": [], "mtime": 0}


def _scan_reference_files() -> list[dict]:
    """Scannt den Referenzordner und gibt Datei-Infos zurück (ohne Bilder zu laden!).
    Schnell, kein Base64, kein RAM-Verbrauch."""
    ref_dir = Path(REFERENCE_IMAGE_DIR)
    if not ref_dir.exists():
        return []

    try:
        dir_mtime = ref_dir.stat().st_mtime
    except OSError:
        return []

    if _reference_cache["files"] and _reference_cache["mtime"] == dir_mtime:
        return _reference_cache["files"]

    extensions = {".png", ".jpg", ".jpeg", ".webp"}
    skip_prefixes = ("bildschirmfoto", "screenshot", ".ds_store")
    files = []
    for img_path in sorted(ref_dir.iterdir()):
        if img_path.suffix.lower() not in extensions:
            continue
        if img_path.name.lower().startswith(skip_prefixes):
            continue
        files.append({
            "path": str(img_path),
            "filename": img_path.name,
            "name_lower": img_path.stem.lower(),  # ohne Extension, lowercase
        })

    _reference_cache["files"] = files
    _reference_cache["mtime"] = dir_mtime
    logger.info(f"Referenzbilder gescannt: {len(files)} Dateien in {REFERENCE_IMAGE_DIR}/")
    return files


def _find_best_reference(order_info: dict) -> tuple:
    """Findet das passendste Referenzbild per Dateiname-Matching.
    Schnell, kostenlos, kein API-Call nötig!

    Dateiname-Konvention: avatar_Netagen.png
    z.B. elsa_3_etagen.png, ronaldo_2_etagen.png

    Returns: (reference_url, explanation, None) oder (None, None, None).
    """
    files = _scan_reference_files()
    if not files:
        logger.info("Keine Referenzbilder vorhanden.")
        return None, None, None

    dekoration = (order_info.get("dekoration") or "").lower()
    anlass = (order_info.get("anlass") or "").lower()
    farbe = (order_info.get("farbe") or "").lower()
    schichten = order_info.get("schichten", "")

    if not dekoration and not anlass:
        return None, None, None

    # Schichten-Zahl extrahieren
    import re as _re
    n_schichten = int(_re.findall(r'\d+', str(schichten))[0]) if _re.findall(r'\d+', str(schichten)) else 0
    etagen_str = f"{n_schichten}_etagen" if n_schichten else ""

    # Keywords aus Dekoration + Anlass extrahieren
    # Farb-Wörter NICHT als Suchbegriff nutzen (sonst matcht "blau" → "cinderella_blau")
    _color_stop_words = {
        "blau", "rot", "grün", "gruen", "gelb", "rosa", "pink", "beige", "weiß", "weiss",
        "schwarz", "lila", "orange", "braun", "hell", "dunkel", "bunt", "fondant", "fundant",
        "mit", "und", "ein", "einem", "einer", "der", "die", "das", "farbe", "deko",
    }
    deko_words = [w for w in dekoration.split() if len(w) > 2 and w not in _color_stop_words]
    # Anlass-Mapping: "Hochzeit" → sucht "hochzeit" im Dateinamen
    if "hochzeit" in anlass:
        deko_words.append("hochzeit")
    if "drip" in dekoration:
        deko_words.append("drip")
    # Braut/Bräutigam → gespeichert als "braut_braeutigam_..."
    if any(kw in dekoration for kw in ["braut", "bräutigam", "brautigam"]):
        deko_words.append("braut")
        deko_words.append("braeutigam")

    best_match = None
    best_score = 0

    for f in files:
        name = f["name_lower"]
        score = 0

        # Jedes Keyword im Dateinamen suchen
        for word in deko_words:
            if word in name:
                score += 2  # Figurenname = hoher Score

        # Etagen-Match bonus
        if etagen_str and etagen_str in name:
            score += 1

        # Farb-Match bonus
        if farbe and farbe in name:
            score += 1

        if score > best_score:
            best_score = score
            best_match = f

    if best_match and best_score >= 2:
        ref_url = f"/referenz/{urllib.parse.quote(best_match['filename'])}"
        explanation = f"Referenzbild gefunden: {best_match['filename']}"

        # Beschreibung aus Dateinamen ableiten — NUR Motiv/Figur, NICHT Farbe!
        # Farbe kommt vom Kundenwunsch, nicht vom Referenzbild
        ref_name = best_match["name_lower"]  # z.B. "ronaldo_3_etagen_rot"
        # Farben aus der Beschreibung entfernen
        _color_words = {"rot", "blau", "gruen", "grün", "gelb", "rosa", "pink",
                        "beige", "weiss", "schwarz", "lila", "orange", "braun"}
        ref_words = [w for w in ref_name.split("_") if w not in _color_words]
        ref_theme = " ".join(ref_words)  # z.B. "ronaldo 3 etagen"
        # Personennamen im Referenz-Thema sanitizen (OpenAI Moderation!)
        _ref_name_replacements = {
            "cinderella": "princess in blue gown",
            "elsa": "ice queen princess",
            "frozen": "ice kingdom themed",
            "ariel": "mermaid princess",
            "rapunzel": "long-haired princess",
            "ronaldo": "soccer player",
            "messi": "soccer player",
            "spiderman": "red blue superhero",
            "batman": "dark superhero",
            "superman": "caped superhero",
            "mickey": "cartoon mouse",
            "paw_patrol": "rescue puppies",
            "paw patrol": "rescue puppies",
            "mascha": "cartoon girl and bear",
            "olaf": "snowman character",
            "mcqueen": "racing car",
            "cars": "racing car",
            "peppa": "cartoon pig",
            "pikachu": "yellow cartoon creature",
            "rotkäppchen": "red riding hood fairy tale",
            "rotkaeppchen": "red riding hood fairy tale",
            "braut_braeutigam": "bride and groom fondant figurines",
            "braut": "bride fondant figurine",
            "braeutigam": "groom fondant figurine",
            "hochzeit_paar": "wedding couple fondant figurines",
        }
        ref_theme_sanitized = ref_theme
        for name, replacement in _ref_name_replacements.items():
            if name in ref_theme_sanitized:
                ref_theme_sanitized = ref_theme_sanitized.replace(name, replacement)

        ref_description = (
            f"A cake with a {ref_theme_sanitized} design/theme from our portfolio. "
            f"IGNORE the colors of the reference — use ONLY the customer's requested colors!"
        )

        logger.info(f"Dateiname-Match: {best_match['filename']} (score={best_score})")
        return ref_url, explanation, ref_description
    else:
        logger.info(f"Kein Dateiname-Match für Dekoration '{dekoration}' (best_score={best_score}).")
        return None, None, None


def _build_reference_filename(order_info: dict) -> str | None:
    """Baut einen beschreibenden Dateinamen für das Referenzbild.
    Format: [figur/anlass]_[N]_etagen.png
    Gibt IMMER einen Dateinamen zurück (für alle approbierten Bestellungen)."""
    import re as _re
    deko = (order_info.get("dekoration") or "").lower()
    anlass = (order_info.get("anlass") or "").lower()
    schichten = order_info.get("schichten", "")
    geschmack = (order_info.get("geschmack") or "").lower()

    # Etagen-Zahl
    n = int(_re.findall(r'\d+', str(schichten))[0]) if _re.findall(r'\d+', str(schichten)) else 0
    etagen = f"_{n}_etagen" if n else ""

    # Bekannte Figuren → figur_Netagen.png (höchste Priorität)
    known_names = [
        "ronaldo", "messi", "neymar", "mbappe", "lewandowski", "haaland",
        "elsa", "anna", "moana", "rapunzel", "ariel", "cinderella",
        "simba", "nemo", "mickey", "micky", "minnie",
        "frozen", "eiskönigin", "olaf",
        "mascha", "winnie_pooh", "winnie pooh", "winnie",
        "spiderman", "spider-man", "batman", "superman", "iron man", "hulk", "thor",
        "harry potter", "mario", "luigi", "pikachu", "pokemon",
        "peppa", "paw patrol", "paw_patrol", "bluey", "mirabel", "encanto",
        "spongebob", "barbie", "einhorn", "unicorn",
        "avatar", "cars", "mcqueen", "lightning",
        "teddy", "panda", "hase", "pferde", "piraten",
        "rotkaeppchen", "rotkäppchen",
    ]
    for name in known_names:
        if name in deko:
            figure = name.replace(" ", "_").replace("-", "")
            return f"{figure}{etagen}.png"

    # Hochzeit mit Braut/Bräutigam-Avatar → Dateiname enthält "braut" damit Suche es findet
    if any(kw in deko for kw in ["braut", "bräutigam", "brautigam", "hochzeitspaar"]):
        return f"braut_braeutigam{etagen}.png"

    # Hochzeitsanlass (ohne spezifische Figur)
    if "hochzeit" in anlass or "hochzeit" in deko:
        farbe = (order_info.get("farbe") or "").lower()
        farbe_part = f"_{farbe[:5]}" if farbe else ""
        return f"hochzeit{farbe_part}{etagen}.png"

    # Geburtstag / sonstige Anlässe → anlass + geschmack + etagen
    anlass_clean = _re.sub(r'[^a-zA-ZäöüÄÖÜß0-9]', '_', anlass)[:15] if anlass else "torte"
    geschmack_clean = geschmack[:5] if geschmack else ""
    parts = [p for p in [anlass_clean, geschmack_clean, etagen.lstrip("_")] if p]
    return "_".join(parts) + ".png" if parts else None


def _auto_save_to_reference(image_url: str, order_info: dict):
    """Speichert generierte Bilder mit bekannten Figuren automatisch im Referenz-Ordner.
    Dateiname: avatar_Netagen.png (z.B. elsa_3_etagen.png)
    So wächst das Portfolio und wird per Dateiname sofort findbar."""
    if not image_url:
        return

    filename = _build_reference_filename(order_info)
    if not filename:
        return  # Kein bekannter Figurenname → nicht speichern

    try:
        src = image_url.lstrip("/")
        if not os.path.isfile(src):
            return

        ref_dir = Path(REFERENCE_IMAGE_DIR)
        ref_dir.mkdir(parents=True, exist_ok=True)

        dest = ref_dir / filename
        if dest.exists():
            logger.info(f"Referenzbild existiert bereits: {dest}")
            return

        import shutil
        shutil.copy2(src, dest)

        # Cache invalidieren
        _reference_cache["mtime"] = 0

        logger.info(f"Figuren-Kuchen gespeichert: {dest} (Deko: {order_info.get('dekoration', '')})")
    except Exception as e:
        logger.warning(f"Auto-Speicherung fehlgeschlagen: {e}")


# ── In-Memory Cache: gleiche Bestellung → fertiges Bild wiederverwenden ──
# Persistiert über Server-Lebenszeit. Datei-Existenz wird beim Lookup geprüft,
# damit gelöschte/aufgeräumte PNGs den Cache nicht falsch beantworten.
_IMAGE_CACHE: dict = {}
_IMAGE_CACHE_MAX = 200


def _image_cache_key(prompt: str) -> str:
    import hashlib
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _image_cache_get(key: str):
    url = _IMAGE_CACHE.get(key)
    if not url:
        return None
    # URL ist /static/images/xxx.png — Datei muss noch existieren
    if url.startswith("/static/") and not os.path.exists(url.lstrip("/")):
        _IMAGE_CACHE.pop(key, None)
        return None
    return url


def _image_cache_put(key: str, url: str) -> None:
    if not url:
        return
    if len(_IMAGE_CACHE) >= _IMAGE_CACHE_MAX:
        # Simpler FIFO-Trim: ältesten Eintrag rauswerfen
        try:
            _IMAGE_CACHE.pop(next(iter(_IMAGE_CACHE)))
        except StopIteration:
            pass
    _IMAGE_CACHE[key] = url


@trace_node("generate_image")
@safe_node(fallback_response="Die Bildgenerierung ist gerade leider nicht verfügbar. Bitte versuchen Sie es in wenigen Minuten erneut oder fahren Sie mit der Bestellung fort.")
def generate_image(state: AgentState) -> AgentState:
    """Generiert EIN Bild: Mehrstöckige Fondant-Torte mit farbigen Etagen.
    Jede Etage hat eine andere Fondant-Farbe, von außen sichtbar.
    Provider-Kette: OpenAI → HuggingFace (automatischer Fallback)."""

    order_info = state.get("order_info", {})
    messages_history = state.get("messages", [])

    # ── Referenzbild-Suche (schnelles Dateiname-Matching) ──
    ref_url, ref_explanation, ref_description = _find_best_reference(order_info)
    # Referenzbild NUR intern für Prompt nutzen — NICHT als 2. Bild anzeigen!
    # state["reference_image_url"] = ref_url  # ← DEAKTIVIERT: Nur EIN Bild anzeigen
    state["reference_image_url"] = None

    description = build_image_description(order_info, messages_history)

    # Beschriftung wird NICHT im Bild gerendert (FLUX kann keinen Text zuverlässig darstellen)
    # Text wird nur in der Bestellung gespeichert und von den Konditoren von Hand aufgetragen
    text_instruction = ""

    schichten = order_info.get("schichten", "")
    fuellung = order_info.get("fuellung", "")
    geschmack = order_info.get("geschmack", "")

    # Füllung in einzelne Schichten aufteilen für bessere Darstellung
    # Unterstützt: "1:schoko, 2:vanille" UND "erdbeer und schoko" UND "erdbeer, schoko"
    import re as _re_fill
    _fuellung_clean = fuellung.replace(".", ":").replace("+", ",")
    # "und" / "and" als Trennzeichen erkennen
    _fuellung_clean = _re_fill.sub(r'\s+und\s+', ',', _fuellung_clean, flags=_re_fill.IGNORECASE)
    _fuellung_clean = _re_fill.sub(r'\s+and\s+', ',', _fuellung_clean, flags=_re_fill.IGNORECASE)
    # Jetzt nach ":" und "," splitten
    _split_parts = _re_fill.split(r'[,:]', _fuellung_clean)
    fuellung_parts = [f.strip() for f in _split_parts if f.strip() and not f.strip().isdigit()]
    if len(fuellung_parts) >= 2:
        layers_visual = ", ".join(fuellung_parts)
        layers_desc = f"{schichten} clearly distinct thick horizontal cake layers stacked on top of each other" if schichten else "multiple thick cake layers"
        filling_desc = f"each layer a different color and flavor ({layers_visual})"
    else:
        layers_desc = f"{schichten} clearly distinct thick horizontal cake layers" if schichten else "multiple layers"
        filling_desc = f"{fuellung} filling" if fuellung else "cream filling"
    sponge_desc = f"{geschmack} sponge" if geschmack else "sponge"

    # ── Anzahl Schichten FRÜHZEITIG berechnen (wird überall gebraucht) ──
    import re as _re_early
    n_layers = int(_re_early.findall(r'\d+', str(schichten))[0]) if _re_early.findall(r'\d+', str(schichten)) else 0

    # ── Farbe explizit für den Prompt extrahieren ──
    farbe = order_info.get("farbe", "")
    deko_raw = order_info.get("dekoration", "")
    deko_color = _extract_color_from_deko(deko_raw)
    primary_color = farbe if farbe else deko_color

    color_instruction = ""
    if primary_color:
        # Prüfe ob mehrere Farben vorhanden sind (z.B. "beige and yellow")
        if " and " in primary_color and n_layers >= 2:
            colors = [c.strip() for c in primary_color.split(" and ")]
            tier_color_desc = []
            positions = ["bottom", "middle", "top"]
            for i, c in enumerate(colors[:n_layers]):
                pos = positions[i] if i < len(positions) else f"tier {i+1}"
                tier_color_desc.append(f"{pos} tier: smooth {c} fondant")
            color_instruction = (
                f"CRITICAL COLOR REQUIREMENT: Each tier MUST be a different fondant color as specified: "
                f"{', '.join(tier_color_desc)}. "
                f"The colors MUST be clearly {primary_color} — no other colors for the exterior! "
            )
        else:
            color_instruction = (
                f"CRITICAL COLOR REQUIREMENT: The cake's fondant/exterior MUST be {primary_color}. "
                f"Do NOT use any other color for the cake exterior. The dominant color is {primary_color}. "
            )

    # ── Form des Kuchens (Herzform, eckig, rund) ──
    form_raw = order_info.get("form", "").lower().strip()
    _shape_map = {"herzform": "heart-shaped", "herz": "heart-shaped",
                  "eckig": "square-shaped", "quadratisch": "square-shaped",
                  "rund": "round"}
    shape_en = _shape_map.get(form_raw, "round")

    # ── EIN kombiniertes Bild: Kuchen mit Schnitt ──
    # n_layers wurde oben bereits berechnet

    # Explizite Schicht-Beschreibung für den Prompt bauen
    # Fondant-Schichten: 3 separate, von außen sichtbare Lagen übereinander
    layer_colors_map = {
        "schoko": "dark brown", "schokolade": "dark brown", "chocolate": "dark brown",
        "vanille": "cream white", "vanilla": "cream white", "vanile": "cream white",
        "erdbeer": "pink/red", "erdbeere": "pink/red", "strawberry": "pink/red",
        "zitrone": "bright yellow", "lemon": "bright yellow",
        "himbeere": "deep red/raspberry", "karamell": "golden caramel", "beeren": "dark purple",
    }

    if n_layers >= 3 and len(fuellung_parts) >= 3:
        layer_descs = []
        positions = ["bottom", "middle", "top"]
        for i, part in enumerate(fuellung_parts[:n_layers]):
            color = layer_colors_map.get(part.lower(), part)
            pos = positions[i] if i < 3 else f"layer {i+1}"
            layer_descs.append(f"{pos} tier {color} fondant")
        tiers_str = ", ".join(layer_descs)
        layers_prompt = (
            f"The cake has EXACTLY {n_layers} separate fondant-covered tiers stacked on top of each other, "
            f"each tier a DIFFERENT COLOR and clearly visible from outside: {tiers_str}. "
            f"Thin cream line between each tier. "
        )
    elif n_layers >= 2:
        layers_prompt = (
            f"The cake has EXACTLY {n_layers} separate fondant-covered tiers stacked on top of each other, "
            f"each tier a different color, clearly visible from outside. "
        )
    else:
        layers_prompt = ""

    # ── Referenzbild-Beschreibung als Vorlage nutzen ──
    reference_prompt = ""
    if ref_description:
        # Kundenwünsche sammeln — diese haben IMMER Vorrang vor dem Referenzbild!
        changes = []
        # Fondant-Farben aus Schichten extrahieren
        fondant_colors = []
        for part in fuellung_parts[:n_layers] if fuellung_parts else []:
            color = layer_colors_map.get(part.lower(), "")
            if color:
                fondant_colors.append(color)
        # Farben aus Dekoration extrahieren — proximity-aware (siehe _extract_color_from_deko)
        deko_color_str = _extract_color_from_deko(deko_raw)
        if deko_color_str:
            for c in deko_color_str.split(" and "):
                if c and c not in fondant_colors:
                    fondant_colors.append(c)

        if fondant_colors:
            changes.append(f"CRITICAL: The fondant colors MUST be {' and '.join(fondant_colors)} — ignore any colors from the reference!")
        elif primary_color:
            changes.append(f"CRITICAL: The fondant color MUST be {primary_color} — ignore any colors from the reference!")

        if schichten:
            changes.append(f"The cake must have exactly {n_layers} tiers")
        beschriftung = order_info.get("beschriftung", "")
        if beschriftung and beschriftung.lower() not in ("keine", "no", "nein", ""):
            changes.append(f"DO NOT render any text on the cake — the inscription '{beschriftung}' will be added by hand later")
        else:
            changes.append("DO NOT render any text or writing on the cake")

        changes_str = ". ".join(changes) + "." if changes else ""

        reference_prompt = (
            f"DESIGN THEME ONLY (not colors!): {ref_description} "
            f"CUSTOMER REQUIREMENTS (override everything else): {changes_str} "
        )
        logger.info(f"Referenz-basierter Prompt aktiv: {reference_prompt[:200]}...")

    # Anschnitt-Beschreibung: zeigt die inneren Schichten mit expliziten Farben
    cut_prompt = ""
    if n_layers >= 2 and fuellung_parts:
        # Explizite Farbbeschreibung für jede Schicht im Anschnitt
        layer_color_descs = []
        for part in fuellung_parts[:n_layers]:
            color = layer_colors_map.get(part.lower(), part)
            layer_color_descs.append(f"{color} {part}")
        cut_prompt = (
            f"The cake has a clean wedge-shaped slice cut out, revealing EXACTLY {n_layers} distinct "
            f"internal sponge layers clearly visible in the cross-section: "
            f"{', '.join(layer_color_descs)}. "
            f"Each internal layer is a DIFFERENT COLOR. Thin cream filling between layers. "
        )
    else:
        cut_prompt = (
            "The cake has a clean wedge-shaped slice cut out, revealing the internal layers "
            f"of {sponge_desc} with {filling_desc}. "
        )

    # Dekoration auf ALLE Schichten verteilen — aber Figuren nur auf die obere Etage!
    deko_raw = order_info.get("dekoration", "")
    deko_all_tiers = ""
    if deko_raw and n_layers >= 2:
        # Avatar/Figuren (Gitarre, Ronaldo etc.) gehören NUR oben drauf
        # Muster/Themen (Schmetterlinge, Blumen, Sterne) über alle Tiers
        has_avatar = any(word in deko_raw.lower() for word in [
            "gitarre", "gittare", "auto", "sportwagen", "rennwagen", "lkw", "traktor",
            "fussball", "fußball", "krone", "rakete", "flugzeug", "schiff", "boot",
            "ballerina", "dinosaurier", "dino", "pferd", "katze", "hund", "bär",
            "junge", "mädchen", "baby", "prinzessin", "prinz", "ritter",
            "spiderman", "elsa", "ronaldo", "messi", "batman", "superman",
            "einhorn", "drache",
        ])
        has_spread_pattern = any(word in deko_raw.lower() for word in [
            "schmetterling", "blumen", "herz", "stern", "noten", "rosen",
        ])
        if has_avatar and not has_spread_pattern:
            # Figur oben, Fondant-Farben auf die Tiers verteilt
            deko_all_tiers = (
                f"CRITICAL FIGURINE REQUIREMENT: A clearly visible fondant figurine matching this exact "
                f"description MUST be placed ON TOP of the cake: '{deko_raw}'. "
                f"The figurine is the centerpiece — it MUST be present and recognizable. "
                f"Each fondant tier should be smooth with its own color as specified. "
            )
        else:
            deko_all_tiers = (
                f"CRITICAL DECORATION RULE: The decoration theme ({deko_raw}) must be spread across ALL {n_layers} tiers, "
                f"not just on the top tier! Every tier should have decorative elements matching the theme. "
            )

    combined_prompt = (
        "IMPORTANT: Generate exactly ONE single photograph. No collage, no grid, no multiple images. "
        f"{reference_prompt}"
        f"{color_instruction}"
        f"Professional food photography of a VERY TALL {shape_en} birthday cake WITH A SLICE CUT OUT showing the inside layers. "
        f"{layers_prompt}"
        f"{cut_prompt}"
        f"{deko_all_tiers}"
        f"The cake is decorated: {description}"
        f"{text_instruction}. "
        f"Single cake, centered composition, clean white background, "
        f"soft studio lighting, appetizing, high-end bakery quality, photorealistic."
    )

    try:
        # ── Cache-Lookup: identische Bestellung → fertiges Bild wiederverwenden ──
        cache_key = _image_cache_key(combined_prompt)
        cached_url = _image_cache_get(cache_key)
        if cached_url:
            logger.info(f"Bildgenerierung: Cache-Hit ({cache_key[:10]}…) → {cached_url}")
            image_url = cached_url
        else:
            image_url = generate_single_image(combined_prompt, "combined", order_info=order_info)
            _image_cache_put(cache_key, image_url)
        state["image_url"] = image_url
        state["image_url_cut"] = None  # Nicht nötig – alles in einem Bild

        # Auto-Save passiert NICHT hier, sondern erst wenn der Kunde bestellt (finalize_order)

        # Antwort basierend auf tatsächlichen order_info – keine Halluzination
        deko_info = order_info.get("dekoration", "")
        farbe_info = order_info.get("farbe", "")
        detail_parts = []
        if deko_info:
            detail_parts.append(f"Dekoration: {deko_info}")
        if farbe_info:
            detail_parts.append(f"Farbe: {farbe_info}")
        detail_str = f" ({', '.join(detail_parts)})" if detail_parts else ""

        beschriftung_hint = ""
        beschriftung = order_info.get("beschriftung", "")
        if beschriftung and beschriftung.lower() not in ("keine", "no", "nein", ""):
            beschriftung_hint = (
                f" 📝 Wir haben die Beschriftung \"{beschriftung}\" notiert — "
                f"sie wird von unseren Konditoren von Hand aufgetragen und ist bei Abholung/Lieferung auf der Torte."
            )

        referenz_hint = ""
        if ref_url:
            referenz_hint = " Dazu haben wir einen ähnlichen Kuchen aus unserem Portfolio gefunden."

        state["response"] = (
            f"Hier ist das Vorschaubild Ihres Wunschkuchens{detail_str} – "
            f"mit Außenansicht und den Schichten im Anschnitt. "
            f"Das finale Produkt kann leicht abweichen.{beschriftung_hint}{referenz_hint} "
            "Gefällt Ihnen das Design?"
        )

    except Exception as e:
        logger.error(f"Bildgenerierung fehlgeschlagen: {type(e).__name__}: {e}")
        state["image_url"] = None
        state["image_url_cut"] = None
        state["response"] = (
            "Das Vorschaubild konnte leider nicht generiert werden. "
            "Bitte versuchen Sie es in wenigen Minuten erneut. "
            "Möchten Sie stattdessen den Preis berechnen?"
        )

    return state


# ═══════════════════════════════════════
# NODE 11: UPDATE ORDER (Änderungen)
# ═══════════════════════════════════════
@trace_node("update_order")
@safe_node(fallback_response="Was möchten Sie an Ihrer Bestellung ändern oder hinzufügen?")
def update_order(state: AgentState) -> AgentState:
    """Verarbeitet Änderungswünsche oder Ergänzungen an der bestehenden Bestellung."""

    order_info_before = dict(state.get("order_info", {}))
    state = extract_info(state)
    order_info_after = state.get("order_info", {})

    # Nur ECHTE neue/geänderte Felder zählen (nicht Formatunterschiede)
    new_keys = set()
    for k, v in order_info_after.items():
        if k not in order_info_before:
            new_keys.add(k)
        elif order_info_before[k] != v:
            # Nur als Änderung zählen wenn sich der Wert wirklich unterscheidet
            old_norm = order_info_before[k].lower().strip()
            new_norm = v.lower().strip() if isinstance(v, str) else str(v)
            if old_norm != new_norm:
                new_keys.add(k)

    # Vage Werte erkennen (z.B. "ja", "deko", "eine") → nachfragen
    vague_values = {"ja", "nein", "eine", "ein", "deko", "dekoration", "auch"}
    vague_keys = set()
    for k in new_keys:
        val = order_info_after.get(k, "").lower().strip()
        if val in vague_values or len(val) <= 3:
            vague_keys.add(k)
            # Vagen Wert wieder entfernen
            if k in order_info_before:
                order_info_after[k] = order_info_before[k]
            else:
                del order_info_after[k]
    state["order_info"] = order_info_after
    new_keys -= vague_keys

    if not new_keys and not vague_keys:
        # Nichts Neues extrahiert — prüfe ob der Kunde etwas wiederholt
        user_input = state.get("user_input", "").lower().strip()
        # Wenn der Kunde denselben Termin nochmal sagt, bestätige kurz
        liefertermin = order_info_after.get("liefertermin", "")
        if liefertermin and any(kw in user_input for kw in ["liefer", "termin", liefertermin.lower()]):
            state["response"] = f"Der Liefertermin {liefertermin} ist bereits notiert. Kann ich sonst noch etwas für Sie tun?"
            return state

        # Sonst: fragen was der Kunde möchte
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
    elif vague_keys and not new_keys:
        # Vage Angaben → konkret nachfragen
        field_questions = get_field_questions()
        field_name = list(vague_keys)[0]
        question = field_questions.get(field_name, f"Was genau möchten Sie für {field_name}?")
        state["response"] = f"Gerne! {question}"
    else:
        # Echte Änderungen bestätigen
        field_labels = {
            "geschmack": "Geschmack", "form": "Form", "schichten": "Schichten",
            "fuellung": "Füllung", "dekoration": "Dekoration", "farbe": "Farbe",
            "anlass": "Anlass", "gaeste": "Gäste",
            "abholung": "Abholung/Lieferung", "lieferadresse": "Lieferadresse",
            "liefertermin": "Liefertermin", "allergien": "Allergien",
            "beschriftung": "Beschriftung",
        }
        changed_labels = [field_labels.get(k, k) for k in new_keys]
        changed = ", ".join(changed_labels)
        state["response"] = (
            f"Perfekt, ich habe {changed} für Sie aktualisiert! "
            f"Möchten Sie noch etwas ändern oder soll ich den aktualisierten Preis berechnen?"
        )
        state = check_complete(state)

    return state


# ═══════════════════════════════════════
# NODE 12: REDIRECT (Off-Topic)
# ═══════════════════════════════════════
@trace_node("redirect")
@safe_node()
def redirect(state: AgentState) -> AgentState:
    """Leitet höflich zurück zum Thema."""
    config = load_prompts_config()
    state["response"] = config["prompts"]["redirect"]
    return state


# ═══════════════════════════════════════
# NODE 13.5: KALENDER-CHECK (cal.com Integration)
# ═══════════════════════════════════════
@safe_node()
def check_calendar(state: AgentState) -> AgentState:
    """
    Prüft ob der gewünschte Liefertermin verfügbar ist.
    Nutzt cal.com API wenn konfiguriert, sonst lokale DB.
    Wird aufgerufen wenn ein Liefertermin extrahiert wurde.
    """
    from services.cal_service import get_available_slots, get_alternative_dates

    order_info = state.get("order_info", {})
    liefertermin = order_info.get("liefertermin", "")

    if not liefertermin:
        # Kein Termin angegeben — nichts zu prüfen
        return state

    # Prüfe ob dieser Termin schon geprüft wurde (um Doppelprüfung zu vermeiden)
    last_checked = state.get("_last_calendar_check", "")
    if last_checked == liefertermin:
        return state

    logger.info(f"Kalender-Check für Liefertermin: {liefertermin}")
    result = get_available_slots(liefertermin)

    # Merken dass dieser Termin geprüft wurde
    state["_last_calendar_check"] = liefertermin

    if result["source"] == "error":
        # Datum konnte nicht geparst werden
        state["response"] = result["message"]
        # Termin zurücksetzen damit erneut gefragt wird
        order_info.pop("liefertermin", None)
        state["order_info"] = order_info
        # Feld als "pending" zurücksetzen
        todo = state.get("question_todo", {})
        if "liefertermin" in todo:
            todo["liefertermin"] = "asked"
            state["question_todo"] = todo
        return state

    if result["available"]:
        # Termin ist frei!
        logger.info(f"Termin {result['date']} ist verfügbar ({result['source']})")
        state["calendar_available"] = True
        state["calendar_message"] = result["message"]
        # Termin im ISO-Format speichern (für DB)
        if result.get("date"):
            order_info["liefertermin"] = result["date"]
            state["order_info"] = order_info
    else:
        # Termin ist NICHT frei — Alternativen suchen
        logger.info(f"Termin {result.get('date', liefertermin)} nicht verfügbar ({result['source']})")
        state["calendar_available"] = False

        # Alternative Termine finden
        alternatives = get_alternative_dates(liefertermin, days_range=7)

        if alternatives:
            alt_list = "\n".join([
                f"  - {alt['date_formatted']}"
                for alt in alternatives[:5]
            ])
            state["response"] = (
                f"{result['message']}\n\n"
                f"Folgende Termine wären noch frei:\n{alt_list}\n\n"
                f"Welcher Termin passt Ihnen?"
            )
        else:
            state["response"] = (
                f"{result['message']} "
                f"Leider sind in den nächsten Tagen alle Termine belegt. "
                f"Bitte nennen Sie einen anderen Wunschtermin."
            )

        # Termin zurücksetzen damit erneut gefragt wird
        order_info.pop("liefertermin", None)
        state["order_info"] = order_info
        state["_last_calendar_check"] = ""  # Reset damit neuer Termin geprüft wird

    return state


# ═══════════════════════════════════════
# NODE 14: FINALIZE (Bestellung abschließen)
# ═══════════════════════════════════════
@trace_node("finalize_order")
@safe_node()
def finalize_order(state: AgentState) -> AgentState:
    """Schließt die Bestellung ab — zeigt Adressformular für Kundendaten."""
    state["order_finalized"] = True
    state["show_address_form"] = True

    # Explizites Flag: Abholung oder Lieferung?
    order_info = state.get("order_info", {})
    abholung_val = (order_info.get("abholung") or "").lower().strip()
    state["is_pickup"] = abholung_val in ("abholung", "selbst abholen", "abholen", "selbstabholung")

    # ── Auto-Save: Erst jetzt wenn Kunde bestellt, Bild ins Portfolio speichern ──
    # WICHTIG: image_url wird am Anfang jedes Runs auf None gesetzt →
    # Das letzte generierte Bild liegt in last_image_url!
    image_url = state.get("image_url") or state.get("last_image_url")
    order_info = state.get("order_info", {})
    if image_url:
        _auto_save_to_reference(image_url, order_info)

    # ── Cal.com: Termin buchen wenn konfiguriert ──
    cal_booking_msg = ""
    liefertermin = order_info.get("liefertermin", "")
    if liefertermin:
        try:
            from cal_service import book_slot, is_configured as cal_configured
            if cal_configured():
                booking = book_slot(
                    date_str=liefertermin,
                    customer_name="Kidstorte-Kunde",  # Wird später mit echtem Namen aktualisiert
                )
                if booking["success"]:
                    cal_booking_msg = f"\n📅 {booking['message']}"
                    logger.info(f"Cal.com Buchung: {booking.get('booking_id', 'lokal')}")
        except Exception as e:
            logger.warning(f"Cal.com Buchung bei Finalize fehlgeschlagen: {e}")

    # Preistabelle anzeigen
    # Priorität: calculated_price (vom LLM) > _estimate_price_table (Fallback)
    price_text = ""
    if state.get("calculated_price"):
        # LLM hat Preis schon berechnet — nur Gesamtsumme anzeigen
        price_text = f"\n\n💰 Gesamtpreis: <b>{state['calculated_price']}</b>"
    else:
        try:
            from services.pdf_order import _estimate_price_table
            table_html, total_str = _estimate_price_table(order_info)
            if table_html:
                state["calculated_price"] = total_str
                price_text = f"\n\n{table_html}"
        except Exception:
            pass

    state["response"] = (
        "Wunderbar! Um Ihre Bestellung abzuschließen, benötige ich noch Ihre Kontaktdaten. "
        "Bitte füllen Sie das folgende Formular aus."
        f"{price_text}"
        f"{cal_booking_msg}"
    )
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


def _extract_color_from_deko(dekoration: str) -> str:
    """Extrahiert NUR die Torten-Fondant-Farbe aus dem Deko-Feld.
    Wenn 'fondant'/'torte'/'kuchen' im Text vorkommt: NUR Farben in deren Nähe nehmen
    (verhindert dass z.B. 'blauer Sportwagen und rosa Fondant' fälschlich blau zur
    Tortenfarbe macht). Sonst Fallback: erste gefundene Farbe."""
    # Längere Tokens zuerst (damit "hellblau" vor "blau" matcht und "light pink" gewinnt)
    color_words = [
        ("hellblau", "light blue"), ("dunkelblau", "dark blue"),
        ("hellrosa", "light pink"), ("hellrose", "light pink"),
        ("hellrosé", "light pink"), ("rosé", "pink"), ("rose", "pink"),
        ("dunkelrot", "dark red"),
        ("hellgrün", "light green"), ("dunkelgrün", "dark green"),
        ("hellgelb", "light yellow"),
        ("blau", "blue"), ("rot", "red"), ("rosa", "pink"), ("pink", "pink"),
        ("grüne", "green"), ("grün", "green"),
        ("gelbe", "yellow"), ("gelb", "yellow"),
        ("weiß", "white"), ("weiss", "white"),
        ("schwarz", "black"), ("lila", "purple"), ("violett", "purple"),
        ("orange", "orange"), ("beige", "beige"), ("gold", "gold"),
        ("silber", "silver"), ("türkis", "turquoise"), ("braun", "brown"),
        ("bunt", "colorful"),
        ("blue", "blue"), ("red", "red"), ("green", "green"),
        ("white", "white"), ("yellow", "yellow"),
    ]

    deko_lower = dekoration.lower()
    cake_anchors = ("fondant", "torte", "kuchen", "cake", "etage", "tier")
    has_anchor = any(a in deko_lower for a in cake_anchors)

    import re as _re_color

    found_colors: list[str] = []

    def _add(en_color: str):
        if en_color not in found_colors:
            found_colors.append(en_color)

    def _extract_in_text(text: str):
        """Extrahiert alle Farben aus einem Textstück (längere Tokens zuerst)."""
        for de, en in color_words:
            if _re_color.search(rf"\b{_re_color.escape(de)}", text):
                _add(en)

    if has_anchor:
        # Clause-Modus: Text an Satzzeichen + "und"/"sowie" splitten,
        # dann NUR Farben aus Klauseln mit Anker extrahieren.
        # Verhindert dass z.B. "roten Kleid, fondantfarbe hellrose" → "rot" rauszieht.
        clauses = _re_color.split(r"[,;.\n]|\bund\b|\bsowie\b|\baber\b", deko_lower)
        any_clause_matched = False
        for clause in clauses:
            if any(a in clause for a in cake_anchors):
                any_clause_matched = True
                _extract_in_text(clause)
        # Notfall-Fallback: keine Klausel mit Anker hat eine Farbe ergeben
        # (z.B. weil Anker und Farbe in derselben unsplittbaren Phrase stehen aber
        # über mehrere Anker verteilt) → den ganzen Text durchsuchen
        if not found_colors and any_clause_matched is False:
            _extract_in_text(deko_lower)
    else:
        # Fallback: kein Anker im Text → einfache Extraktion (alte Logik)
        _extract_in_text(deko_lower)

    if len(found_colors) >= 2:
        return " and ".join(found_colors)
    elif found_colors:
        return found_colors[0]
    return ""


def build_image_description(order_info, messages):
    """Baut eine detaillierte englische Beschreibung für den Bild-Prompt.
    Übersetzt deutsche Deko-Begriffe in konkrete visuelle Beschreibungen."""
    parts = []

    farbe = order_info.get("farbe", "")
    deko_raw = order_info.get("dekoration", "")
    deko_color = _extract_color_from_deko(deko_raw)
    primary_color = farbe if farbe else deko_color

    if primary_color:
        parts.append(f"fondant color: {primary_color}")
    if order_info.get("anlass"):
        parts.append(f"{order_info['anlass']} celebration cake")
    if order_info.get("geschmack"):
        parts.append(f"{order_info['geschmack']} flavor")
    if order_info.get("form"):
        form_map = {"herzform": "heart-shaped", "herz": "heart-shaped",
                     "eckig": "square-shaped", "quadratisch": "square-shaped",
                     "rund": "round"}
        form_en = form_map.get(order_info["form"].lower().strip(), order_info["form"])
        parts.append(f"{form_en} cake")
    if order_info.get("schichten"):
        parts.append(f"{order_info['schichten']} tiers")
    if order_info.get("fuellung"):
        parts.append(f"{order_info['fuellung']} filling")

    # Deko-Beschreibung: detailliert und auf Englisch
    if deko_raw:
        deko_desc = _translate_deko_to_prompt(deko_raw)
        parts.append(deko_desc)

    if parts:
        return ", ".join(parts)

    return "Ein schöner Geburtstagskuchen mit Dekoration"


def _translate_deko_to_prompt(deko: str) -> str:
    """Übersetzt deutsche Deko-Beschreibung in detaillierten englischen Bild-Prompt.
    z.B. 'beige fondant und gelbe fondant und als avatar eine gitarre'
    → 'decorated with a detailed realistic 3D fondant acoustic guitar figurine on top'
    """
    deko_lower = deko.lower()

    # Avatar/Figuren erkennen und detailliert beschreiben
    _avatar_descriptions = {
        "gitarre": "a detailed realistic 3D fondant acoustic guitar figurine with strings, body and neck clearly visible",
        "gittare": "a detailed realistic 3D fondant acoustic guitar figurine with strings, body and neck clearly visible",
        "e-gitarre": "a detailed realistic 3D fondant electric guitar figurine with pickups and fretboard",
        "klavier": "a detailed 3D fondant grand piano figurine with keys and lid",
        "fussball": "a detailed 3D fondant soccer ball with black and white hexagonal pattern",
        "fußball": "a detailed 3D fondant soccer ball with black and white hexagonal pattern",
        "auto": "a detailed 3D fondant race car figurine",
        "einhorn": "a detailed 3D fondant unicorn figurine with horn, mane and tail",
        "schmetterling": "detailed 3D fondant butterfly figurines with colorful wings",
        "schmetterlinge": "multiple detailed 3D fondant butterfly figurines with colorful wings spread across all tiers",
        "blumen": "detailed 3D fondant flower decorations (roses, daisies) spread across all tiers",
        "herz": "detailed 3D fondant heart decorations",
        "herzen": "multiple detailed 3D fondant heart decorations spread across all tiers",
        "stern": "detailed 3D fondant star decorations",
        "sterne": "multiple detailed 3D fondant star decorations spread across all tiers",
        "krone": "a detailed 3D golden fondant crown on top",
        "dinosaurier": "a detailed 3D fondant dinosaur figurine",
        "dino": "a detailed 3D fondant dinosaur figurine",
        "pferd": "a detailed 3D fondant horse figurine",
        "katze": "a detailed 3D fondant cat figurine",
        "hund": "a detailed 3D fondant dog figurine",
        "bär": "a detailed 3D fondant teddy bear figurine",
        "rakete": "a detailed 3D fondant rocket ship figurine",
        "ballerina": "a detailed 3D fondant ballerina figurine in a tutu",
        "musik": "detailed 3D fondant musical note decorations",
        "noten": "detailed 3D fondant musical note decorations spread across tiers",
    }

    found_avatars = []
    for keyword, description in _avatar_descriptions.items():
        if keyword in deko_lower:
            found_avatars.append(description)

    if found_avatars:
        return f"decorated with {', '.join(found_avatars)} as the main cake topper"

    # Fallback: generische Fondant-Deko
    # Farb-Wörter und "fondant" entfernen für den Deko-Kern
    import re as _re_deko
    _color_words_de = {"beige", "gelb", "gelbe", "blau", "rot", "rosa", "pink", "grün",
                       "grüne", "weiß", "schwarz", "lila", "orange", "gold", "silber"}
    _noise_words = {"fondant", "und", "mit", "als", "eine", "ein", "einem"}
    words = _re_deko.split(r'\s+', deko_lower)
    theme_words = [w for w in words if w not in _color_words_de and w not in _noise_words and len(w) > 1]
    if theme_words:
        return f"decorated with {' '.join(theme_words)} themed fondant decoration"
    return "with elegant fondant decoration"
