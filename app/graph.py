"""
Graph – Verbindet die Nodes mit Edges und Routing-Logik.

Dies ist das Herzstück des Agenten: Es definiert den Ablauf.
Jetzt STATELESS: Bekommt State als Parameter, gibt aktualisierten State zurück.
Session-Management wird extern vom SessionManager übernommen.

Ablauf:
    ┌──────────────────┐
    │  classify_intent  │
    └────────┬─────────┘
             │
    ┌────────┴──────────────────────────────────┐
    │        │         │       │       │         │
 greeting  order    price   image   info     offtopic
    │        │         │       │       │         │
  greet  extract   retrieve retrieve retrieve redirect
    │    info       docs    docs    docs        │
    │      │         │       │       │          │
    │   check      calc   generate answer      │
    │   complete   price   image   question     │
    │      │                                    │
    │   ┌──┴──┐                                 │
    │  ask   summarize                          │
    │  next  order                              │
    │                                           │
    └───────────────────┬───────────────────────┘
                        │
                    RESPONSE
"""

import logging
import time
from app.state import AgentState
from monitoring.tracing import trace_run, is_enabled as tracing_enabled
from app.nodes import (
    guardrail,
    classify_and_extract,
    greet,
    extract_info,
    check_complete,
    ask_next,
    summarize_order,
    retrieve_docs,
    calculate_price,
    answer_question,
    generate_image,
    update_order,
    redirect,
    finalize_order,
    check_calendar,
)
from app.state import get_required_fields

logger = logging.getLogger("Kidstorte")


class CakeDreamsGraph:
    """
    Stateless Agent-Graph: Bekommt State, läuft die Nodes durch,
    gibt aktualisierten State zurück.
    Session-Persistenz wird extern vom SessionManager gehandhabt.
    """

    def run(self, state: AgentState, user_input: str) -> AgentState:
        """
        Führt einen kompletten Durchlauf durch den Graphen aus.

        Args:
            state: Der aktuelle Session-State (aus ChromaDB geladen)
            user_input: Die Nachricht des Kunden

        Returns:
            Aktualisierter State mit response und optional image_url
        """
        t0 = time.time()

        # Fehlende Felder initialisieren (leere/neue Session)
        if "messages" not in state:
            state["messages"] = []
        if "order_info" not in state:
            state["order_info"] = {}
        if "question_todo" not in state:
            # TODO-Liste einmalig initialisieren: alle Pflichtfelder → "pending"
            required = get_required_fields()
            state["question_todo"] = {f: "pending" for f in required}

        # Reset pro Durchlauf
        state["user_input"] = user_input
        state["response"] = ""
        # Letztes Bild merken (für PDF), aktuelles zurücksetzen
        if state.get("image_url"):
            state["last_image_url"] = state["image_url"]
        state["image_url"] = None
        state["guardrail_blocked"] = False
        state["show_address_form"] = False  # Formular nur bei explizitem Trigger zeigen

        # User-Nachricht zum Verlauf hinzufügen
        state["messages"].append({"role": "user", "content": user_input})

        # Nur die letzten 20 Nachrichten behalten
        if len(state["messages"]) > 20:
            state["messages"] = state["messages"][-20:]

        # ── SCHRITT 0: GUARDRAIL – Eingabe prüfen ──
        state = guardrail(state)
        if state.get("guardrail_blocked"):
            logger.warning(f"Guardrail hat Eingabe blockiert: '{user_input[:60]}'")
            state["messages"].append({
                "role": "assistant",
                "content": state["response"]
            })
            return state

        # ── SCHRITT 1: Intent erkennen + Infos extrahieren
        # (1 LLM-Call) ──
        state = classify_and_extract(state)
        intent = state["intent"]

        # ── SCHRITT 1b: Nach Bestellabschluss → keine Änderungen mehr erlauben ──
        # order_finalized=True wird gesetzt wenn der Kunde das Adressformular ausfüllt.
        # Danach darf er nicht mehr Dekoration/Preis/Form etc. ändern — nur noch neue Bestellung.
        if state.get("order_finalized") and intent not in ("greeting", "info", "offtopic", "price"):
            state["response"] = (
                "Ihre Bestellung wurde bereits aufgenommen! 🎂 "
                "Möchten Sie eine neue Bestellung aufgeben? "
                "Sagen Sie einfach 'Hallo' oder 'Neue Bestellung starten'."
            )
            state["messages"].append({"role": "assistant", "content": state["response"]})
            return state

        # ── SCHRITT 2: Routing basierend auf Intent ──
        if intent == "greeting":
            # Begrüßung = neues Gespräch → alles zurücksetzen inkl. Messages
            state["order_info"] = {}
            state["order_complete"] = False
            state["order_finalized"] = False
            state["address_asked"] = False
            state["missing_fields"] = []
            state["messages"] = []  # Alte Nachrichten löschen!
            # TODO-Liste zurücksetzen: alle Felder wieder auf "pending"
            required = get_required_fields()
            state["question_todo"] = {f: "pending" for f in required}
            logger.info("Neue Session: TODO-Liste zurückgesetzt")
            state = greet(state)

        elif intent == "order":
            # Merken ob Bestellung vorher schon komplett war
            was_complete_before = state.get("order_complete", False)

            # extract_info wurde bereits im combined-Call erledigt
            state = check_complete(state)

            # ── Kalender-Check: Wenn Liefertermin neu angegeben wurde ──
            order_info = state.get("order_info", {})
            liefertermin = order_info.get("liefertermin", "")
            last_checked = state.get("_last_calendar_check", "")
            if liefertermin and liefertermin != last_checked:
                state = check_calendar(state)
                # Wenn Termin nicht verfügbar: Response wurde gesetzt, nicht weiter
                if state.get("calendar_available") is False:
                    # Antwort enthält bereits Alternativen — Bestellung bleibt offen
                    state["messages"].append({"role": "assistant", "content": state["response"]})
                    return state
                # Wenn verfügbar: Kalender-Nachricht an Antwort anhängen
                cal_msg = state.get("calendar_message", "")
                if cal_msg:
                    state["_pending_calendar_msg"] = cal_msg

            if state["order_complete"] and not was_complete_before:
                # Erste Mal komplett → Zusammenfassung + Vorschaubild generieren
                state = summarize_order(state)
                summary_text = state["response"]
                # Zusammenfassung als Nachricht speichern BEVOR Bild generiert wird
                state["messages"].append({"role": "assistant", "content": summary_text})
                # Automatisch Vorschaubild generieren
                logger.info("Alle Felder komplett → generiere automatisch Vorschaubild")
                state = generate_image(state)
                # Zusammenfassung + Bild-Response kombinieren
                state["response"] = f"{summary_text}\n\n{state['response']}"
            elif state["order_complete"] and was_complete_before:
                # War schon komplett, Kunde hat optionale Infos ergänzt (z.B. Lieferadresse)
                # → Nur bestätigen, nicht nochmal summarize
                new_info = state.get("user_input", "")
                order_info = state.get("order_info", {})
                added = []
                if order_info.get("lieferadresse"):
                    added.append(f"Lieferadresse: {order_info['lieferadresse']}")
                if order_info.get("liefertermin"):
                    added.append(f"Liefertermin: {order_info['liefertermin']}")
                # Kalender-Hinweis anhängen wenn vorhanden
                cal_msg = state.pop("_pending_calendar_msg", "")
                if added:
                    response_text = (
                        f"Perfekt, ich habe das notiert: {', '.join(added)}. "
                    )
                    if cal_msg:
                        response_text += f"\n{cal_msg} "
                    response_text += "Kann ich sonst noch etwas für Sie tun?"
                    state["response"] = response_text
                else:
                    state["response"] = (
                        "Ich habe die Info gespeichert. "
                        "Kann ich sonst noch etwas für Sie tun?"
                    )
            else:
                state = ask_next(state)

        elif intent == "price":
            state = retrieve_docs(state)
            state = calculate_price(state)

        elif intent == "image":
            # Erst prüfen ob alle Pflichtfelder beantwortet sind
            state = check_complete(state)
            missing = state.get("missing_fields", [])
            if missing:
                # Noch fehlende Felder → erst diese abfragen, dann Bild
                logger.info(f"Bild angefragt, aber noch {len(missing)} Felder offen: {missing}")
                state["response"] = (
                    f"Gerne zeige ich Ihnen ein Vorschaubild! Vorher brauche ich noch ein paar Infos. "
                )
                state = ask_next(state)
                # Hinweis anhängen dass Bild kommt
                state["response"] = state["response"] + " Danach generiere ich sofort Ihr Vorschaubild! 🎨"
            else:
                state = generate_image(state)

        elif intent == "info":
            state = retrieve_docs(state)
            state = answer_question(state)

        elif intent == "change":
            state = update_order(state)

        elif intent == "finalize":
            # ── Bereits finalisiert? Nicht nochmal fragen ──
            if state.get("order_finalized"):
                state["response"] = (
                    "Ihre Bestellung wurde bereits aufgenommen! "
                    "Möchten Sie eine neue Bestellung starten?"
                )
            else:
                # ── Sicherheitscheck: Sind wirklich ALLE Pflichtfelder da? ──
                was_complete_before = state.get("order_complete", False)
                state = check_complete(state)
                if not state["order_complete"]:
                    # Noch Felder offen → zurück zum Order-Flow, NICHT finalisieren!
                    logger.info(f"Finalize abgelehnt: noch {len(state['missing_fields'])} Felder offen → ask_next")
                    state = ask_next(state)
                elif state["order_complete"] and not was_complete_before:
                    # Bestellung wurde GERADE erst komplett (z.B. abholung war letztes Feld)
                    logger.info("Finalize-Intent, aber Bestellung gerade erst komplett → summarize + image")
                    state = summarize_order(state)
                    summary_text = state["response"]
                    state["messages"].append({"role": "assistant", "content": summary_text})
                    state = generate_image(state)
                    state["response"] = f"{summary_text}\n\n{state['response']}"
                elif not state.get("image_url") and not state.get("last_image_url") and not state.get("_image_gen_failed"):
                    logger.info("Finalize ohne Vorschaubild → generiere erst Bild")
                    state = generate_image(state)
                    # Wenn Bildgenerierung fehlschlägt, merken damit wir nicht endlos loopen
                    if not state.get("image_url"):
                        state["_image_gen_failed"] = True
                else:
                    # Direkt Formular zeigen (kein extra Bestätigungsschritt)
                    state = finalize_order(state)

        elif intent == "offtopic":
            state = redirect(state)

        else:
            state["response"] = "Wie kann ich Ihnen helfen?"

        # Bot-Antwort zum Verlauf hinzufügen
        state["messages"].append({
            "role": "assistant",
            "content": state["response"]
        })

        # ── Graph-Level Trace in LangSmith ──
        duration_ms = (time.time() - t0) * 1000
        try:
            with trace_run(
                "graph_run",
                run_type="chain",
                inputs={"user_input": user_input, "session_id": state.get("session_id", "")},
                metadata={"intent": state.get("intent", ""), "duration_ms": round(duration_ms)},
            ) as run:
                run.end(outputs={
                    "intent": state.get("intent", ""),
                    "response": (state.get("response", "") or "")[:300],
                    "order_complete": state.get("order_complete", False),
                    "image_url": state.get("image_url", ""),
                    "missing_fields": state.get("missing_fields", []),
                    "duration_ms": round(duration_ms),
                })
                run._ended = True
                run.patch()
        except Exception:
            pass  # Tracing-Fehler nie propagieren

        return state
