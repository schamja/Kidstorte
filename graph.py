"""
Graph – Verbindet die Nodes mit Edges und Routing-Logik.

Dies ist das Herzstück des Agenten: Es definiert den Ablauf.
Implementiert das LangGraph-Pattern (Nodes + Edges + State) ohne die Library selbst.

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


class CakeDreamsGraph:
    """
    Der Agent-Graph: Nimmt eine Nachricht, routet sie durch die Nodes,
    und gibt eine Antwort zurück.
    """

    def __init__(self):
        # Persistenter State über die gesamte Konversation
        self.state: AgentState = {
            "user_input": "",
            "messages": [],
            "intent": "",
            "order_info": {},
            "missing_fields": [],
            "order_complete": False,
            "context": "",
            "sources": [],
            "response": "",
            "image_url": None,
        }

    def run(self, user_input: str) -> AgentState:
        """
        Führt einen kompletten Durchlauf durch den Graphen aus.
        Input: Kundennachricht
        Output: Aktualisierter State mit response und optional image_url
        """

        # Reset pro Durchlauf
        self.state["user_input"] = user_input
        self.state["response"] = ""
        self.state["image_url"] = None

        # User-Nachricht zum Verlauf hinzufügen
        self.state["messages"].append({"role": "user", "content": user_input})

        # Nur die letzten 20 Nachrichten behalten
        if len(self.state["messages"]) > 20:
            self.state["messages"] = self.state["messages"][-20:]

        # ── SCHRITT 1: Intent erkennen ──
        self.state = classify_intent(self.state)
        intent = self.state["intent"]

        # ── SCHRITT 2: Routing basierend auf Intent ──
        if intent == "greeting":
            self.state = greet(self.state)

        elif intent == "order":
            self.state = extract_info(self.state)
            self.state = check_complete(self.state)

            if self.state["order_complete"]:
                self.state = summarize_order(self.state)
            else:
                self.state = ask_next(self.state)

        elif intent == "price":
            self.state = retrieve_docs(self.state)
            self.state = calculate_price(self.state)

        elif intent == "image":
            self.state = generate_image(self.state)

        elif intent == "info":
            self.state = retrieve_docs(self.state)
            self.state = answer_question(self.state)

        elif intent == "change":
            self.state = update_order(self.state)

        elif intent == "offtopic":
            self.state = redirect(self.state)

        else:
            self.state["response"] = "Wie kann ich Ihnen helfen?"

        # Bot-Antwort zum Verlauf hinzufügen
        self.state["messages"].append({
            "role": "assistant",
            "content": self.state["response"]
        })

        return self.state

    def reset(self):
        """Setzt den gesamten State zurück (neues Gespräch)."""
        self.state = {
            "user_input": "",
            "messages": [],
            "intent": "",
            "order_info": {},
            "missing_fields": [],
            "order_complete": False,
            "context": "",
            "sources": [],
            "response": "",
            "image_url": None,
        }

    def get_order_info(self):
        """Gibt die aktuell gesammelten Bestellinfos zurück."""
        return self.state.get("order_info", {})
