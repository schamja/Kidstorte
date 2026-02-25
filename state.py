"""
State – Das zentrale Datenobjekt das alle Nodes lesen und schreiben.
Wie ein Klemmbrett das von Station zu Station weitergereicht wird.
"""

from typing import TypedDict, Optional
from config import load_prompts_config

##ein Klemmbrett
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

    # Session
    session_id: str                     # Eindeutige Session-ID (thread_id)

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


def get_required_fields() -> list:
    """Lädt Pflichtfelder aus Config (hot-reloadable)."""
    config = load_prompts_config()
    return config.get("required_fields",
                       ["anlass", "gaeste", "geschmack", "form", "schichten", "fuellung", "dekoration"])


def get_field_questions() -> dict:
    """Lädt Feld-Fragen aus Config (hot-reloadable)."""
    config = load_prompts_config()
    return config.get("field_questions", {})
