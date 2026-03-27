"""
Cal.com Integration – Prüft Bäckerei-Verfügbarkeit und bucht Termine.

Nutzt die cal.com API v2 um:
1. Freie Slots für ein Datum abzufragen
2. Einen Termin zu buchen wenn der Kunde bestellt
3. Alternative Termine vorzuschlagen wenn gewünschtes Datum voll ist

Wenn kein CAL_API_KEY konfiguriert ist, fällt das System auf die
lokale SQLite-basierte Verfügbarkeitsprüfung zurück (order_db.py).
"""

import os
import logging
import datetime
import requests
from typing import Optional

logger = logging.getLogger("kidstorte.calendar")

# ── Konfiguration ──
CAL_API_KEY = os.getenv("CAL_API_KEY", "")
CAL_EVENT_TYPE_ID = os.getenv("CAL_EVENT_TYPE_ID", "")  # Event-Type in cal.com (z.B. "Tortenabholung")
CAL_USERNAME = os.getenv("CAL_USERNAME", "")              # cal.com Username für Slot-Abfrage
CAL_API_VERSION = os.getenv("CAL_API_VERSION", "2024-08-13")
CAL_BASE_URL = "https://api.cal.com/v2"
CAL_TIMEZONE = os.getenv("CAL_TIMEZONE", "Europe/Berlin")

# Öffnungszeiten der Bäckerei (Fallback wenn cal.com nicht konfiguriert)
BAKERY_OPEN_HOUR = int(os.getenv("BAKERY_OPEN_HOUR", "8"))
BAKERY_CLOSE_HOUR = int(os.getenv("BAKERY_CLOSE_HOUR", "18"))
# Sonntag (6) standardmäßig geschlossen
BAKERY_CLOSED_DAYS = [int(d) for d in os.getenv("BAKERY_CLOSED_DAYS", "6").split(",") if d.strip()]


def is_configured() -> bool:
    """Prüft ob cal.com konfiguriert ist."""
    return bool(CAL_API_KEY and (CAL_EVENT_TYPE_ID or CAL_USERNAME))


def _headers() -> dict:
    """Standard-Header für cal.com API."""
    return {
        "Authorization": f"Bearer {CAL_API_KEY}",
        "cal-api-version": CAL_API_VERSION,
        "Content-Type": "application/json",
    }


def _parse_german_date(date_str: str) -> Optional[datetime.date]:
    """
    Parst deutsche Datumsangaben in verschiedenen Formaten:
    - "25.03.2026", "25.3.2026"
    - "2026-03-25"
    - "25. März 2026", "25. März"
    - "nächsten Samstag", "übernächsten Freitag"
    - "in 2 Wochen"
    """
    if not date_str:
        return None

    date_str = date_str.strip().lower()

    # ISO-Format: 2026-03-25
    try:
        return datetime.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass

    # Deutsches Format: 25.03.2026 oder 25.3.2026
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d.%m."):
        try:
            parsed = datetime.datetime.strptime(date_str, fmt).date()
            # Wenn Jahr fehlt (Format "25.03."), aktuelles/nächstes Jahr nehmen
            if fmt.endswith("."):
                today = datetime.date.today()
                parsed = parsed.replace(year=today.year)
                if parsed < today:
                    parsed = parsed.replace(year=today.year + 1)
            return parsed
        except ValueError:
            continue

    # Deutsche Monatsnamen
    _months_de = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12,
        "jan": 1, "feb": 2, "mär": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9,
        "okt": 10, "nov": 11, "dez": 12,
    }
    # "25. März 2026" oder "25. März"
    import re
    match = re.match(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})?", date_str)
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3)) if match.group(3) else datetime.date.today().year
        month = _months_de.get(month_name)
        if month:
            try:
                result = datetime.date(year, month, day)
                if not match.group(3) and result < datetime.date.today():
                    result = result.replace(year=year + 1)
                return result
            except ValueError:
                pass

    # Relative Angaben: "nächsten Samstag", "nächsten Montag"
    _weekdays_de = {
        "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
        "freitag": 4, "samstag": 5, "sonntag": 6,
    }
    for day_name, weekday in _weekdays_de.items():
        if day_name in date_str:
            today = datetime.date.today()
            days_ahead = (weekday - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Nächste Woche
            if "übernächst" in date_str:
                days_ahead += 7
            return today + datetime.timedelta(days=days_ahead)

    # "in X Wochen" / "in X Tagen"
    match = re.match(r"in\s+(\d+)\s+(woche|tag)", date_str)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        days = amount * 7 if "woche" in unit else amount
        return datetime.date.today() + datetime.timedelta(days=days)

    # "morgen", "übermorgen"
    today = datetime.date.today()
    if "übermorgen" in date_str:
        return today + datetime.timedelta(days=2)
    if "morgen" in date_str:
        return today + datetime.timedelta(days=1)

    logger.warning(f"Konnte Datum nicht parsen: '{date_str}'")
    return None


def get_available_slots(date_str: str) -> dict:
    """
    Prüft Verfügbarkeit für ein bestimmtes Datum.

    Returns:
        {
            "available": True/False,
            "date": "2026-03-25",
            "slots": ["09:00", "10:00", ...],  # Freie Uhrzeiten
            "message": "Beschreibung für den Kunden",
            "source": "calcom" | "local",  # Woher die Info kommt
        }
    """
    target_date = _parse_german_date(date_str)
    if not target_date:
        return {
            "available": False,
            "date": None,
            "slots": [],
            "message": f"Das Datum '{date_str}' konnte ich leider nicht verstehen. "
                       f"Bitte nennen Sie ein Datum im Format TT.MM.JJJJ (z.B. 25.03.2026).",
            "source": "error",
        }

    date_iso = target_date.isoformat()
    today = datetime.date.today()

    # Validierung: Mindestens 2 Tage Vorlauf
    if target_date <= today + datetime.timedelta(days=1):
        return {
            "available": False,
            "date": date_iso,
            "slots": [],
            "message": f"Der {target_date.strftime('%d.%m.%Y')} ist leider zu kurzfristig. "
                       f"Wir brauchen mindestens 2 Tage Vorlauf für die Zubereitung.",
            "source": "validation",
        }

    # Prüfe Wochentag (Bäckerei-Ruhetage)
    if target_date.weekday() in BAKERY_CLOSED_DAYS:
        day_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        closed_day = day_names[target_date.weekday()]
        return {
            "available": False,
            "date": date_iso,
            "slots": [],
            "message": f"Am {closed_day}, den {target_date.strftime('%d.%m.%Y')}, haben wir leider geschlossen.",
            "source": "validation",
        }

    # ── Cal.com API abfragen ──
    if is_configured():
        return _check_calcom_availability(target_date)

    # ── Fallback: Lokale DB-Prüfung ──
    return _check_local_availability(target_date)


def _check_calcom_availability(target_date: datetime.date) -> dict:
    """Prüft Verfügbarkeit über cal.com API."""
    date_iso = target_date.isoformat()
    next_day = (target_date + datetime.timedelta(days=1)).isoformat()

    params = {
        "start": date_iso,
        "end": next_day,
        "timeZone": CAL_TIMEZONE,
    }

    # Event-Type ID oder Username + Slug
    if CAL_EVENT_TYPE_ID:
        params["eventTypeId"] = CAL_EVENT_TYPE_ID
    elif CAL_USERNAME:
        params["username"] = CAL_USERNAME

    try:
        resp = requests.get(
            f"{CAL_BASE_URL}/slots",
            headers=_headers(),
            params=params,
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            slots_data = data.get("data", {})

            # Cal.com gibt Slots als {date: [slot1, slot2, ...]} zurück
            all_slots = []
            for day_key, day_slots in slots_data.items():
                for slot in day_slots:
                    time_str = slot.get("time", slot.get("start", ""))
                    if time_str:
                        # Nur Uhrzeit extrahieren (HH:MM)
                        if "T" in time_str:
                            time_str = time_str.split("T")[1][:5]
                        all_slots.append(time_str)

            if all_slots:
                slots_formatted = ", ".join(all_slots[:6])  # Max 6 Slots zeigen
                return {
                    "available": True,
                    "date": date_iso,
                    "slots": all_slots,
                    "message": f"Am {target_date.strftime('%d.%m.%Y')} haben wir noch freie Termine: "
                               f"{slots_formatted} Uhr. 🗓️",
                    "source": "calcom",
                }
            else:
                return {
                    "available": False,
                    "date": date_iso,
                    "slots": [],
                    "message": f"Am {target_date.strftime('%d.%m.%Y')} sind leider keine Termine mehr frei.",
                    "source": "calcom",
                }

        elif resp.status_code == 401:
            logger.error("Cal.com API: Ungültiger API-Key!")
            return _check_local_availability(target_date)  # Fallback

        else:
            logger.warning(f"Cal.com API Fehler {resp.status_code}: {resp.text[:200]}")
            return _check_local_availability(target_date)  # Fallback

    except requests.exceptions.Timeout:
        logger.warning("Cal.com API Timeout — nutze lokale Prüfung")
        return _check_local_availability(target_date)
    except Exception as e:
        logger.error(f"Cal.com API Fehler: {e}")
        return _check_local_availability(target_date)


def _check_local_availability(target_date: datetime.date) -> dict:
    """Fallback: Lokale Verfügbarkeitsprüfung über SQLite."""
    from services.order_db import count_orders_on_date
    from app.config import load_prompts_config

    date_iso = target_date.isoformat()
    config = load_prompts_config()
    max_per_day = config.get("max_orders_per_day", 5)

    current_orders = count_orders_on_date(date_iso)
    remaining = max_per_day - current_orders

    if remaining > 0:
        return {
            "available": True,
            "date": date_iso,
            "slots": [f"{h}:00" for h in range(BAKERY_OPEN_HOUR, BAKERY_CLOSE_HOUR)],
            "message": f"Am {target_date.strftime('%d.%m.%Y')} haben wir noch Kapazität "
                       f"({remaining} von {max_per_day} Plätzen frei). 🗓️",
            "source": "local",
        }
    else:
        return {
            "available": False,
            "date": date_iso,
            "slots": [],
            "message": f"Am {target_date.strftime('%d.%m.%Y')} sind wir leider schon ausgebucht "
                       f"(max. {max_per_day} Bestellungen pro Tag).",
            "source": "local",
        }


def get_alternative_dates(around_date: str, days_range: int = 7) -> list:
    """
    Sucht alternative freie Termine rund um ein gewünschtes Datum.

    Returns: Liste von {date, slots, message} Dicts (max 5 Alternativen)
    """
    target = _parse_german_date(around_date)
    if not target:
        target = datetime.date.today() + datetime.timedelta(days=3)

    alternatives = []
    today = datetime.date.today()

    for delta in range(-days_range, days_range + 1):
        check_date = target + datetime.timedelta(days=delta)

        # Überspringe vergangene Tage und zu kurzfristige
        if check_date <= today + datetime.timedelta(days=1):
            continue
        # Überspringe Ruhetage
        if check_date.weekday() in BAKERY_CLOSED_DAYS:
            continue

        result = get_available_slots(check_date.isoformat())
        if result["available"]:
            alternatives.append({
                "date": result["date"],
                "date_formatted": check_date.strftime("%d.%m.%Y (%A)").replace(
                    "Monday", "Montag").replace("Tuesday", "Dienstag").replace(
                    "Wednesday", "Mittwoch").replace("Thursday", "Donnerstag").replace(
                    "Friday", "Freitag").replace("Saturday", "Samstag").replace(
                    "Sunday", "Sonntag"),
                "slots_count": len(result["slots"]),
            })

        if len(alternatives) >= 5:
            break

    return alternatives


def book_slot(
    date_str: str,
    customer_name: str,
    customer_email: str = "",
    time_slot: str = "10:00",
) -> dict:
    """
    Bucht einen Termin bei cal.com (optional — nur wenn konfiguriert).

    Returns:
        {"success": True/False, "booking_id": "...", "message": "..."}
    """
    if not is_configured():
        logger.info("Cal.com nicht konfiguriert — Buchung übersprungen (lokal verwaltet)")
        return {
            "success": True,
            "booking_id": None,
            "message": "Termin lokal gespeichert (cal.com nicht konfiguriert).",
        }

    target_date = _parse_german_date(date_str)
    if not target_date:
        return {
            "success": False,
            "booking_id": None,
            "message": f"Ungültiges Datum: {date_str}",
        }

    # Zeitpunkt zusammenbauen: 2026-03-25T10:00:00
    start_time = f"{target_date.isoformat()}T{time_slot}:00"

    payload = {
        "start": start_time,
        "attendee": {
            "name": customer_name or "Kidstorte-Kunde",
            "email": customer_email or "kunde@kidstorte.de",
            "timeZone": CAL_TIMEZONE,
        },
    }

    if CAL_EVENT_TYPE_ID:
        payload["eventTypeId"] = int(CAL_EVENT_TYPE_ID)

    try:
        resp = requests.post(
            f"{CAL_BASE_URL}/bookings",
            headers=_headers(),
            json=payload,
            timeout=15,
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            booking_data = data.get("data", {})
            booking_id = booking_data.get("uid", booking_data.get("id", ""))
            logger.info(f"Cal.com Buchung erfolgreich: {booking_id}")
            return {
                "success": True,
                "booking_id": str(booking_id),
                "message": f"Termin am {target_date.strftime('%d.%m.%Y')} um {time_slot} Uhr gebucht!",
            }
        else:
            logger.warning(f"Cal.com Buchung fehlgeschlagen: {resp.status_code} {resp.text[:200]}")
            return {
                "success": False,
                "booking_id": None,
                "message": f"Terminbuchung fehlgeschlagen (cal.com: {resp.status_code}). "
                           f"Der Termin wurde aber lokal gespeichert.",
            }

    except Exception as e:
        logger.error(f"Cal.com Buchungsfehler: {e}")
        return {
            "success": False,
            "booking_id": None,
            "message": "Terminbuchung bei cal.com fehlgeschlagen, aber lokal gespeichert.",
        }
