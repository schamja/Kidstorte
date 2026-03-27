# Implementierungsplan: Adressformular, Reset-Button, DB + Admin-Aktualisierung

## Übersicht der 3 Anforderungen

1. **Adressformular im Chat** — Name, Adresse, PLZ, Stadt, Telefon, Email als Formular; 
Speicherung in DB; E-Mail an Designer + Kunde
2. **Reset-Button nach Bestellabschluss** — Button zum Zurücksetzen nach Finalisierung
3. **DB-Diagramm + Admin-Panel bei jeder Bestellung aktualisieren**

---

## Schritt 1: SQLite-Datenbank für Bestellungen (`order_db.py` — NEUE Datei)

- Neue SQLite-Datenbank `kidstorte.db` mit Tabelle `orders`:
  ```
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  session_id      TEXT
  order_info      TEXT (JSON)      -- Kuchen-Details
  customer_name   TEXT
  customer_email  TEXT
  customer_phone  TEXT
  customer_street TEXT
  customer_plz    TEXT
  customer_city   TEXT
  liefertermin    TEXT
  total_price     TEXT
  status          TEXT DEFAULT 'neu'
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  ```
- Funktionen: `save_order()`, `get_all_orders()`, `get_order_stats()`, `get_order(id)`

## Schritt 2: E-Mail-Versand (`email_service.py` — NEUE Datei)

- SMTP-Konfiguration über .env: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `DESIGNER_EMAIL`
- `send_order_email(order_data, recipient_type)` — sendet an Designer oder Kunde
- HTML-Template für Bestätigungs-E-Mail mit Bestellübersicht-Tabelle
- Fehlertoleranz: Wenn SMTP nicht konfiguriert → nur loggen, kein Crash

## Schritt 3: Config erweitern (`config.py`)

- Neue .env-Variablen: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `DESIGNER_EMAIL`, `SHOP_NAME`

## Schritt 4: Adressformular im Chat (Frontend)

### `templates/index.html`
- Neuer HTML-Block: `<div id="address-form-container">` (versteckt)
- Formularfelder: Name, Adresse, PLZ, Stadt, Telefon, E-Mail
- Submit-Button "Bestellung abschicken"

### `static/script.js`
- `showAddressForm()` — zeigt das Formular im Chat-Bereich
- `submitAddress()` — sendet Formulardaten an neuen API-Endpoint `/api/submit-order`
- Wird aufgerufen wenn `order_finalized: true` in der API-Response
- Nach erfolgreichem Submit → Bestätigung + Reset-Button anzeigen

### `static/style.css`
- Styles für `.address-form` im Chat-Widget

## Schritt 5: Neuer API-Endpoint (`main.py`)

- `POST /api/submit-order` — empfängt Adressformular-Daten + Session-ID
  1. Lädt order_info aus Session
  2. Speichert in SQLite (`order_db.save_order()`)
  3. Sendet E-Mail an Designer (`email_service`)
  4. Sendet Bestätigungs-E-Mail an Kunden
  5. Gibt Erfolgs-Response zurück

## Schritt 6: Flow-Änderung (Finalize → Formular → Reset)

### `nodes.py` — `finalize_order()`
- Response ändern: statt Abschiedsnachricht → "Bitte geben Sie Ihre Kontaktdaten ein..."
- Neues Flag `show_address_form: true` im State setzen

### `main.py` — API-Response
- `show_address_form` in Response aufnehmen

### `script.js` — Flow
1. Bestellung komplett → Preis/Bild abfragen
2. "fertig/keine Wünsche" → `finalize` → Bot zeigt Formular-Aufforderung + **Adressformular erscheint**
3. Kunde füllt aus + klickt "Absenden" → `/api/submit-order`
4. Bestätigung + **"Neue Bestellung starten"** Button erscheint

## Schritt 7: Admin-Panel aktualisieren (`templates/admin.html`)

- Neue Sektion: **"Bestellungen"** — Tabelle mit allen Bestellungen aus SQLite
  - Spalten: ID, Datum, Kunde, Kuchen, Preis, Status
- Statistiken erweitern: Bestellungen heute, Umsatz gesamt
- Auto-Refresh oder manuelle Aktualisierung

### `main.py` — Admin-Endpoints erweitern
- `GET /admin` — lädt jetzt auch Bestellungen aus SQLite
- `POST /admin/orders/{id}/status` — Status ändern (neu → in Bearbeitung → fertig)

## Schritt 8: ER-Diagramm erstellen (`er-diagramm.html`)

- HTML-Seite mit visuellem Diagramm der Datenstruktur
- Zeigt: orders-Tabelle, ChromaDB Sessions, ChromaDB cake_chunks
- Beziehungen: Session → Order (1:1)

---

## Geänderte Dateien

| Datei | Aktion |
|-------|--------|
| `order_db.py` | **NEU** — SQLite DB-Modul |
| `email_service.py` | **NEU** — SMTP E-Mail-Versand |
| `config.py` | Erweitern um SMTP + DB Konfiguration |
| `main.py` | `/api/submit-order` Endpoint + Admin-Erweiterung |
| `nodes.py` | `finalize_order()` anpassen (show_address_form) |
| `state.py` | `show_address_form` Flag |
| `templates/index.html` | Adressformular HTML |
| `static/script.js` | Formular-Logik + neuer Submit-Flow |
| `static/style.css` | Formular-Styles |
| `templates/admin.html` | Bestellungen-Sektion + erweiterte Stats |
| `er-diagramm.html` | **NEU** — Datenbank-Diagramm |
| `session_manager.py` | `order_finalized` persistieren |
