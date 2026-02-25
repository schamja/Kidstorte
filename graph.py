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
from state import AgentState
from nodes import (
    classify_intent,
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
)

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

        # Reset pro Durchlauf
        state["user_input"] = user_input
        state["response"] = ""
        state["image_url"] = None

        # User-Nachricht zum Verlauf hinzufügen
        state["messages"].append({"role": "user", "content": user_input})

        # Nur die letzten 20 Nachrichten behalten
        if len(state["messages"]) > 20:
            state["messages"] = state["messages"][-20:]

        # ── SCHRITT 1: Intent erkennen ──
        state = classify_intent(state)
        intent = state["intent"]

        # ── SCHRITT 2: Routing basierend auf Intent ──
        if intent == "greeting":
            state = greet(state)

        elif intent == "order":
            state = extract_info(state)
            state = check_complete(state)

            if state["order_complete"]:
                state = summarize_order(state)
            else:
                state = ask_next(state)

        elif intent == "price":
            state = retrieve_docs(state)
            state = calculate_price(state)

        elif intent == "image":
            state = generate_image(state)

        elif intent == "info":
            state = retrieve_docs(state)
            state = answer_question(state)

        elif intent == "change":
            state = update_order(state)

        elif intent == "offtopic":
            state = redirect(state)

        else:
            state["response"] = "Wie kann ich Ihnen helfen?"

        # Bot-Antwort zum Verlauf hinzufügen
        state["messages"].append({
            "role": "assistant",
            "content": state["response"]
        })

        return state
