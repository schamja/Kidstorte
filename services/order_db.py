"""
Order Database – SQLite-basierte Bestellungsverwaltung.
Speichert alle abgeschlossenen Bestellungen mit Kundendaten.
"""

import sqlite3
import json
import time
import logging
from pathlib import Path

logger = logging.getLogger("kidstorte")

DB_PATH = Path(__file__).parent / "kidstorte.db"


def _get_connection():
    """Erstellt eine SQLite-Verbindung mit WAL-Modus."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Erstellt alle Tabellen falls sie nicht existieren."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            order_info TEXT,
            customer_name TEXT,
            customer_email TEXT,
            customer_phone TEXT,
            customer_street TEXT,
            customer_plz TEXT,
            customer_city TEXT,
            liefertermin TEXT,
            total_price TEXT,
            status TEXT DEFAULT 'neu',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER REFERENCES orders(id),
            rating INTEGER CHECK(rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Order-DB initialisiert")


def save_order(session_id: str, order_info: dict, customer_data: dict) -> int:
    """
    Speichert eine neue Bestellung.
    Returns: Die neue Order-ID.
    """
    conn = _get_connection()
    cursor = conn.execute("""
        INSERT INTO orders (
            session_id, order_info, customer_name, customer_email,
            customer_phone, customer_street, customer_plz, customer_city,
            liefertermin, total_price
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        json.dumps(order_info, ensure_ascii=False),
        customer_data.get("name", ""),
        customer_data.get("email", ""),
        customer_data.get("phone", ""),
        customer_data.get("street", ""),
        customer_data.get("plz", ""),
        customer_data.get("city", ""),
        order_info.get("liefertermin", ""),
        customer_data.get("total_price", ""),
    ))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Bestellung #{order_id} gespeichert (Session: {session_id[:12]}...)")
    return order_id


def get_all_orders() -> list:
    """Gibt alle Bestellungen zurück (neueste zuerst)."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT * FROM orders ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_order(order_id: int) -> dict | None:
    """Gibt eine einzelne Bestellung zurück."""
    conn = _get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_order_status(order_id: int, status: str) -> bool:
    """Ändert den Status einer Bestellung."""
    valid_statuses = ["neu", "in_bearbeitung", "fertig", "storniert"]
    if status not in valid_statuses:
        return False
    conn = _get_connection()
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()
    logger.info(f"Bestellung #{order_id} Status → {status}")
    return True


def delete_order(order_id: int) -> bool:
    """Löscht eine stornierte Bestellung endgültig aus der Datenbank.
    Nur Bestellungen mit Status 'storniert' dürfen gelöscht werden."""
    conn = _get_connection()
    row = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row or row[0] != "storniert":
        conn.close()
        return False
    conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    logger.info(f"Stornierte Bestellung #{order_id} endgültig gelöscht")
    return True


def get_order_stats() -> dict:
    """Gibt Bestellungs-Statistiken zurück."""
    conn = _get_connection()
    total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    today = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')"
    ).fetchone()[0]
    by_status = {}
    for row in conn.execute("SELECT status, COUNT(*) as cnt FROM orders GROUP BY status"):
        by_status[row[0]] = row[1]
    conn.close()
    return {
        "total_orders": total,
        "orders_today": today,
        "by_status": by_status,
    }


def get_orders_per_day(month: str) -> dict:
    """Zählt Bestellungen pro Liefertermin-Tag für einen Monat (Format: YYYY-MM)."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT liefertermin, COUNT(*) as cnt FROM orders "
        "WHERE liefertermin LIKE ? AND status != 'storniert' "
        "GROUP BY liefertermin",
        (f"{month}%",)
    ).fetchall()
    conn.close()
    return {row["liefertermin"]: row["cnt"] for row in rows if row["liefertermin"]}


def get_available_dates(days_ahead: int = 60, max_per_day: int = 5) -> list:
    """Gibt Liste freier Daten (als YYYY-MM-DD) für die nächsten N Tage zurück."""
    import datetime
    today = datetime.date.today()
    available = []
    conn = _get_connection()
    for i in range(2, days_ahead + 1):  # ab übermorgen
        day = today + datetime.timedelta(days=i)
        day_str = day.isoformat()
        count = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE liefertermin = ? AND status != 'storniert'",
            (day_str,)
        ).fetchone()[0]
        if count < max_per_day:
            available.append(day_str)
    conn.close()
    return available


def count_orders_on_date(date_str: str) -> int:
    """Zählt Bestellungen für ein bestimmtes Datum."""
    conn = _get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE liefertermin = ? AND status != 'storniert'",
        (date_str,)
    ).fetchone()[0]
    conn.close()
    return count


# --- Bewertungen ---

def save_rating(order_id: int, rating: int, comment: str = "") -> int:
    """Speichert eine neue Bewertung. Returns: Rating-ID."""
    conn = _get_connection()
    cursor = conn.execute(
        "INSERT INTO ratings (order_id, rating, comment) VALUES (?, ?, ?)",
        (order_id, rating, comment)
    )
    rating_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Bewertung gespeichert: Order #{order_id}, {rating} Sterne")
    return rating_id


def get_rating(order_id: int) -> dict | None:
    """Gibt die Bewertung für eine Bestellung zurück."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT * FROM ratings WHERE order_id = ?", (order_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_ratings() -> list:
    """Gibt alle Bewertungen mit Kundennamen zurück (neueste zuerst)."""
    conn = _get_connection()
    rows = conn.execute("""
        SELECT r.*, o.customer_name, o.customer_email
        FROM ratings r
        LEFT JOIN orders o ON r.order_id = o.id
        ORDER BY r.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_rating_stats() -> dict:
    """Gibt Bewertungs-Statistiken zurück."""
    conn = _get_connection()
    total = conn.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
    avg = conn.execute("SELECT AVG(rating) FROM ratings").fetchone()[0]
    conn.close()
    return {
        "total_ratings": total,
        "average_rating": round(avg, 1) if avg else 0,
    }


# DB beim Import initialisieren
init_db()
