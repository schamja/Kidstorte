"""
State – Das zentrale Datenobjekt das alle Nodes lesen und schreiben.
Wie ein Klemmbrett das von Station zu Station weitergereicht wird.
"""

from typing import TypedDict, Optional, Literal
from app.config import load_prompts_config

# Status-Werte für jeden Frageschritt im TODO-System
QuestionStatus = Literal["pending", "asked", "answered"]

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
    allergien: str       # Allergien / Unverträglichkeiten (Gluten, Nüsse, Laktose, Eier …)
    beschriftung: str    # Text auf dem Kuchen (z.B. "Happy Birthday Max!")
    abholung: str        # Abholung im Laden oder Lieferung?
    lieferadresse: str   # Lieferadresse (nur bei Lieferung)
    liefertermin: str    # Wunsch-Liefertermin (optional)


class AgentState(TypedDict, total=False):
    """Der gesamte Zustand des Agenten – wird zwischen Nodes geteilt."""

    # Session
    session_id: str                     # Eindeutige Session-ID (thread_id)

    # Input
    user_input: str                     # Aktuelle Nachricht des Kunden

    # Konversation
    messages: list                      # Gesamter Gesprächsverlauf [{role, content}]

    # Intent-Erkennung
    intent: str                         # greeting, order, price, image, info, change, finalize, offtopic
    order_finalized: bool               # Kunde hat keine weiteren Wünsche
    show_address_form: bool             # Adressformular anzeigen
    is_pickup: bool                     # True = Abholung, False = Lieferung

    # Bestellinfos
    order_info: OrderInfo               # Gesammelte Bestelldetails
    missing_fields: list                # Welche Infos noch fehlen
    order_complete: bool                # Sind alle Infos da?

    # RAG
    context: str                        # Aus ChromaDB abgerufene Dokumente
    sources: list                       # Quellen-Metadaten

    # TODO-Liste: Welche Felder wurden gefragt / beantwortet?
    # Werte: "pending" | "asked" | "answered"
    # Beispiel: {"anlass": "answered", "gaeste": "asked", "geschmack": "pending"}
    question_todo: dict

    # Guardrail: True wenn die letzte Nachricht blockiert wurde
    guardrail_blocked: bool

    # Finalize-Flow: Wurde Adresse bereits angefragt?
    address_asked: bool

    # Kalender (cal.com Integration)
    calendar_available: Optional[bool]   # Ist der Wunschtermin verfügbar?
    calendar_message: Optional[str]      # Nachricht zur Verfügbarkeit

    # Output
    response: str                       # Antwort an den Kunden
    image_url: Optional[str]            # Generiertes Bild Außenansicht
    image_url_cut: Optional[str]        # Generiertes Bild Anschnittansicht
    reference_image_url: Optional[str]  # Passendes Referenzbild aus Portfolio
    calculated_price: Optional[str]      # Vom LLM berechneter Gesamtpreis (z.B. "100 €")


def get_required_fields() -> list:
    """Lädt Pflichtfelder aus Config (hot-reloadable)."""
    config = load_prompts_config()
    return config.get("required_fields",
                       ["anlass", "gaeste", "geschmack", "form", "schichten", "fuellung", "dekoration"])


def get_field_questions() -> dict:
    """Lädt Feld-Fragen aus Config (hot-reloadable)."""
    config = load_prompts_config()
    return config.get("field_questions", {})
