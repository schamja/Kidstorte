"""
State – Das zentrale Datenobjekt das alle Nodes lesen und schreiben.
Wie ein Klemmbrett das von Station zu Station weitergereicht wird.
"""

from typing import TypedDict, Optional


class OrderInfo(TypedDict, total=False):
    """Alle Infos die wir für eine Bestellung sammeln."""
    anlass: str          # Geburtstag, Hochzeit, etc.
    gaeste: str          # Anzahl Gäste
    geschmack: str       # Schokolade, Vanille, etc.
    form: str            # Rund, Eckig, Herzform
    schichten: str       # Anzahl Schichten
    fuellung: str        # Himbeere, Schoko, etc.
    dekoration: str      # Fondant, Motivkuchen, etc.
    farbe: str           # Rosa, Blau, etc.


class AgentState(TypedDict, total=False):
    """Der gesamte Zustand des Agenten – wird zwischen Nodes geteilt."""

    # Input
    user_input: str                     # Aktuelle Nachricht des Kunden

    # Konversation
    messages: list                      # Gesamter Gesprächsverlauf [{role, content}]

    # Intent-Erkennung
    intent: str                         # greeting, order, price, image, info, change, offtopic

    # Bestellinfos
    order_info: OrderInfo               # Gesammelte Bestelldetails
    missing_fields: list                # Welche Infos noch fehlen
    order_complete: bool                # Sind alle Infos da?

    # RAG
    context: str                        # Aus ChromaDB abgerufene Dokumente
    sources: list                       # Quellen-Metadaten

    # Output
    response: str                       # Antwort an den Kunden
    image_url: Optional[str]            # Generiertes Bild (falls vorhanden)


# Felder die wir für eine vollständige Bestellung brauchen
REQUIRED_FIELDS = ["anlass", "gaeste", "geschmack", "form", "schichten", "fuellung", "dekoration"]

# Mapping: Feld → Frage die der Bot stellt
FIELD_QUESTIONS = {
    "anlass": "Für welchen Anlass darf der Kuchen sein?",
    "gaeste": "Für wie viele Gäste soll der Kuchen sein?",
    "geschmack": "Welche Geschmacksrichtung soll es sein? Wir haben Schokolade, Vanille, Beeren (vegan), Erdbeere, Karamell und Zitrone (glutenfrei).",
    "form": "In welcher Form hätten Sie den Kuchen gerne – rund, eckig oder als Herzform?",
    "schichten": "Wie viele Schichten soll der Kuchen haben?",
    "fuellung": "Welche Füllung darf es sein?",
    "dekoration": "Möchten Sie eine besondere Dekoration? Zum Beispiel einfache Deko, Fondant, Spezialdesign oder ein Motivkuchen?",
    "farbe": "Haben Sie einen Farbwunsch für den Kuchen?"
}
