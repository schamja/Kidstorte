"""
PDF-Bestellbestätigung für Kidstorte.
Generiert ein professionelles PDF mit Bestelldetails für den Kunden.
"""

import json
import logging
from io import BytesIO
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
)

logger = logging.getLogger("kidstorte")

# Farben passend zum Kidstorte-Webseiten-Design (Petrol/Teal-Palette)
# Aus static/style.css :root → CSS vars
# Aliase BRAUN/BRAUN_HELL bleiben für Rückwärtskompatibilität, mappen aber jetzt
# auf Petrol/Teal — so muss der restliche Code nicht angefasst werden.
PETROL       = colors.HexColor("#0E6B61")   # --color-brown (Webseite Primärfarbe)
PETROL_DARK  = colors.HexColor("#225049")   # --color-brown-dark
PETROL_LIGHT = colors.HexColor("#7DAFA6")   # --color-accent-hover
ACCENT       = colors.HexColor("#3F8378")   # --color-accent
CREAM        = colors.HexColor("#E3FDFB")   # --color-cream (Mint-Hellton)
WARM         = colors.HexColor("#DFE5E4")   # --color-warm
BRAUN        = PETROL                       # Alias → Header-Banner
BRAUN_HELL   = ACCENT                       # Alias → Sub-Banner / Linien
BRAUN_BG     = CREAM                        # Alias → Hintergrund-Sektionen
GRAU         = colors.HexColor("#666666")
HELLGRAU     = colors.HexColor("#f5f5f5")
GREEN        = PETROL_DARK                  # Section-Headlines
WEISS        = colors.white

# Logo-Pfad (relativ zu Projekt-Root)
LOGO_PATH    = Path(__file__).resolve().parent.parent / "logo.png"

PDF_DIR = Path("static/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)

# Preistabelle (Klein/Mittel/Groß/XL)
PRICE_TABLE = {
    "schokolade":  {"klein": 35, "mittel": 60, "groß": 85, "xl": 110},
    "chocolate":   {"klein": 35, "mittel": 60, "groß": 85, "xl": 110},
    "schoko":      {"klein": 35, "mittel": 60, "groß": 85, "xl": 110},
    "vanille":     {"klein": 30, "mittel": 55, "groß": 80, "xl": 105},
    "vanilla":     {"klein": 30, "mittel": 55, "groß": 80, "xl": 105},
    "beeren":      {"klein": 35, "mittel": 58, "groß": 82, "xl": 108},
    "berry":       {"klein": 35, "mittel": 58, "groß": 82, "xl": 108},
    "erdbeere":    {"klein": 35, "mittel": 60, "groß": 85, "xl": 112},
    "erdbeer":     {"klein": 35, "mittel": 60, "groß": 85, "xl": 112},
    "strawberry":  {"klein": 35, "mittel": 60, "groß": 85, "xl": 112},
    "karamell":    {"klein": 38, "mittel": 65, "groß": 90, "xl": 118},
    "caramel":     {"klein": 38, "mittel": 65, "groß": 90, "xl": 118},
    "zitrone":     {"klein": 38, "mittel": 65, "groß": 90, "xl": 118},
    "lemon":       {"klein": 38, "mittel": 65, "groß": 90, "xl": 118},
}

SIZE_MAP = {
    range(1, 7):    "klein",    # ≤6 Gäste = Klein
    range(7, 13):   "mittel",   # 7-12 Gäste = Mittel
    range(13, 21):  "groß",     # 13-20 Gäste = Groß
    range(21, 31):  "xl",       # 21-30 Gäste = XL
    range(31, 51):  "xxl",      # 31-50 Gäste = XXL (XL × 1.5)
    range(51, 500): "event",    # 51+ Gäste = Event (XL × 2)
}

# Dekorations-Aufpreise
DEKO_PRICES = {
    "einfach": 0, "standard": 0, "keine": 0,
    "fondant": 25,
    "spezialdesign": 20, "spezial": 20,
    "motivkuchen": 35, "motiv": 35,
}
# Avatar/Figur-Deko-Keywords → +30€
AVATAR_KEYWORDS = [
    "spiderman", "spider-man", "elsa", "frozen", "paw patrol", "mickey",
    "ronaldo", "messi", "fußballer", "fussballer", "avatar", "figur",
    "superman", "batman", "pirat", "einhorn", "unicorn", "dinosaurier",
    "prinzessin", "cinderella", "winnie", "teddy", "olaf", "mascha",
    "braut", "bräutigam", "brautigam", "hochzeitspaar",
]

# Form-Aufpreise
FORM_PRICES = {
    "rund": 0, "eckig": 0,
    "herzform": 10, "herz": 10,
}

# Füllungs-Aufpreise
FUELLUNG_PRICES = {
    "buttercreme": 0, "butter": 0,
    "sahne": 0, "vanillecreme": 0, "vanille": 0,
    "schokocreme": 5, "schoko": 5, "ganache": 5, "schokolade": 5,
    "frucht": 8, "erdbeer": 8, "himbeer": 8, "mango": 8, "maracuja": 8,
    "nuss": 8, "nougat": 8, "pistazie": 8,
    "karamell": 5, "käsecreme": 5, "frischkäse": 5,
}


def _estimate_price(order_info: dict) -> str | None:
    """Schätzt den Preis basierend auf Geschmack und Gästezahl."""
    geschmack = (order_info.get("geschmack") or "").lower().strip()
    gaeste_raw = order_info.get("gaeste", "")

    # Gästezahl extrahieren
    import re
    numbers = re.findall(r'\d+', str(gaeste_raw))
    gaeste = int(numbers[0]) if numbers else 0

    # Größe bestimmen
    size = "mittel"  # Default
    for r, s in SIZE_MAP.items():
        if gaeste in r:
            size = s
            break

    # Fuzzy-Matching: "vanile" → "vanille", "schoko" → "schokolade" etc.
    _flavor_aliases = {
        "vanil": "vanille", "schoko": "schokolade", "erdbeer": "erdbeere",
        "karamel": "karamell", "zitronen": "zitrone", "beer": "beeren",
        "chocolate": "schokolade", "strawberry": "erdbeere",
    }
    # Erst exaktes Match, dann Fuzzy
    matched_flavor = None
    for flavor_key in PRICE_TABLE:
        if flavor_key in geschmack:
            matched_flavor = flavor_key
            break
    if not matched_flavor:
        for alias, canonical in _flavor_aliases.items():
            if alias in geschmack:
                matched_flavor = canonical
                break

    # Basierpreis finden
    base_prices = None
    for flavor_key, prices in PRICE_TABLE.items():
        if flavor_key == matched_flavor:
            base_prices = prices
            break

    if not base_prices:
        # Fallback: Vanille-Preise
        base_prices = {"klein": 30, "mittel": 55, "groß": 80, "xl": 105}

    # Basispreis nach Größe
    if size in ("klein", "mittel", "groß"):
        base = base_prices.get(size, base_prices.get("mittel", 55))
    elif size == "xl":
        base = base_prices.get("xl", 105)
    elif size == "xxl":
        base = int(base_prices.get("xl", 105) * 1.5)
    elif size == "event":
        base = int(base_prices.get("xl", 105) * 2)
    else:
        base = base_prices.get("mittel", 55)

    # Schichten-Aufpreis: +15€ pro ZUSÄTZLICHE Schicht (ab 2. Schicht)
    schichten = order_info.get("schichten", "")
    try:
        n_schichten = int(re.findall(r'\d+', str(schichten))[0]) if schichten else 1
    except (IndexError, ValueError):
        n_schichten = 1
    schichten_extra = max(0, (n_schichten - 1)) * 15

    # Dekorations-Aufpreis
    deko = (order_info.get("dekoration") or "").lower().strip()
    deko_extra = 0
    for deko_key, deko_price in DEKO_PRICES.items():
        if deko_key in deko:
            deko_extra = deko_price
            break
    # Avatar/Figur-Deko prüfen → +30€ extra
    avatar_extra = 0
    for kw in AVATAR_KEYWORDS:
        if kw in deko:
            avatar_extra = 30
            break
    deko_extra += avatar_extra

    # Wenn keine bekannte Deko erkannt aber Text vorhanden → Einfache Deko (0 €)
    # Kein automatisches Spezialdesign — LLM entscheidet das im Chat

    # Form-Aufpreis
    form_val = (order_info.get("form") or "").lower().strip()
    form_extra = 0
    for form_key, form_price in FORM_PRICES.items():
        if form_key in form_val:
            form_extra = form_price
            break

    # Lieferungs-Aufpreis
    abholung = (order_info.get("abholung") or "").lower().strip()
    liefer_extra = 0
    if abholung in ("lieferung", "liefern", "liefern bitte"):
        liefer_extra = 20  # Umkreis als Default

    total = base + schichten_extra + deko_extra + form_extra + liefer_extra

    size_label = {
        "klein":  f"Klein ({gaeste} Gäste)",
        "mittel": f"Mittel ({gaeste} Gäste)",
        "groß":   f"Groß ({gaeste} Gäste)",
        "xl":     f"XL ({gaeste} Gäste)",
        "xxl":    f"XXL ({gaeste} Gäste)",
        "event":  f"Event ({gaeste} Gäste)",
    }
    return f"ca. {total} € ({size_label.get(size, size)})"


def _estimate_price_table(order_info: dict) -> str | None:
    """Gibt eine vollständige HTML-Preistabelle zurück (wie calculate_price im Chat).
    Wird in finalize_order genutzt wenn kein calculated_price vorhanden ist."""
    geschmack = (order_info.get("geschmack") or "").lower().strip()
    gaeste_raw = order_info.get("gaeste", "")
    import re

    numbers = re.findall(r'\d+', str(gaeste_raw))
    gaeste = int(numbers[0]) if numbers else 0

    size = "mittel"
    for r, s in SIZE_MAP.items():
        if gaeste in r:
            size = s
            break

    _flavor_aliases = {
        "vanil": "vanille", "schoko": "schokolade", "erdbeer": "erdbeere",
        "karamel": "karamell", "zitronen": "zitrone", "beer": "beeren",
        "chocolate": "schokolade", "strawberry": "erdbeere",
    }
    matched_flavor = None
    for flavor_key in PRICE_TABLE:
        if flavor_key in geschmack:
            matched_flavor = flavor_key
            break
    if not matched_flavor:
        for alias, canonical in _flavor_aliases.items():
            if alias in geschmack:
                matched_flavor = canonical
                break

    base_prices = PRICE_TABLE.get(matched_flavor) or {"klein": 30, "mittel": 55, "groß": 80, "xl": 105}

    if size in ("klein", "mittel", "groß"):
        base = base_prices.get(size, base_prices.get("mittel", 55))
    elif size == "xl":
        base = base_prices.get("xl", 105)
    elif size == "xxl":
        base = int(base_prices.get("xl", 105) * 1.5)
    elif size == "event":
        base = int(base_prices.get("xl", 105) * 2)
    else:
        base = base_prices.get("mittel", 55)

    size_labels = {
        "klein": "Klein", "mittel": "Mittel", "groß": "Groß",
        "xl": "XL", "xxl": "XXL", "event": "Event",
    }

    schichten = order_info.get("schichten", "")
    try:
        n_schichten = int(re.findall(r'\d+', str(schichten))[0]) if schichten else 1
    except (IndexError, ValueError):
        n_schichten = 1
    schichten_extra = max(0, (n_schichten - 1)) * 15

    deko = (order_info.get("dekoration") or "").lower().strip()
    deko_extra = 0
    deko_label = ""
    for deko_key, deko_price in DEKO_PRICES.items():
        if deko_key in deko:
            deko_extra = deko_price
            deko_label = deko_key.capitalize()
            break
    avatar_extra = 0
    for kw in AVATAR_KEYWORDS:
        if kw in deko:
            avatar_extra = 30
            deko_label = "Avatar/Figur"
            break
    deko_extra += avatar_extra

    form_val = (order_info.get("form") or "").lower().strip()
    form_extra = 0
    for form_key, form_price in FORM_PRICES.items():
        if form_key in form_val:
            form_extra = form_price
            break

    abholung = (order_info.get("abholung") or "").lower().strip()
    liefer_extra = 0
    if abholung in ("lieferung", "liefern", "liefern bitte"):
        liefer_extra = 20

    geschmack_display = geschmack.capitalize() if geschmack else "Standard"
    size_display = size_labels.get(size, size.capitalize())

    # Füllungs-Aufpreis berechnen
    fuellung_val = (order_info.get("fuellung") or "").lower().strip()
    fuellung_extra = 0
    for fk, fp in FUELLUNG_PRICES.items():
        if fk in fuellung_val:
            fuellung_extra = fp
            break
    fuellung_display = order_info.get("fuellung") or "Standard"

    total = base + schichten_extra + deko_extra + form_extra + liefer_extra + fuellung_extra

    rows = []
    # 1. Grundpreis (Größe + Gäste)
    rows.append(f'<tr><td>💵 Grundpreis ({size_display}, {gaeste} Gäste)</td><td>{base} €</td></tr>')
    # 2. Geschmackspreis
    rows.append(f'<tr><td>🍫 Geschmack ({geschmack_display})</td><td>inklusive</td></tr>')
    # 3. Schichtenpreis
    if schichten_extra > 0:
        rows.append(f'<tr><td>🔢 Schichtenpreis ({n_schichten} Etagen, {n_schichten - 1} extra × 15 €)</td><td>+ {schichten_extra} €</td></tr>')
    else:
        rows.append(f'<tr><td>🔢 Schichtenpreis ({n_schichten} Etage)</td><td>inklusive</td></tr>')
    # 4. Füllungspreis
    if fuellung_extra > 0:
        rows.append(f'<tr><td>🥧 Füllungspreis ({fuellung_display})</td><td>+ {fuellung_extra} €</td></tr>')
    else:
        rows.append(f'<tr><td>🥧 Füllungspreis ({fuellung_display})</td><td>inklusive</td></tr>')
    # 5. Dekoration: Fondant und Avatar als getrennte Zeilen
    if deko_extra > 0:
        base_deko = deko_extra - avatar_extra
        if base_deko > 0:
            fondant_label = "Fondant" if avatar_extra > 0 else (deko_label or "Dekoration")
            rows.append(f'<tr><td>✨ {fondant_label}</td><td>+ {base_deko} €</td></tr>')
        if avatar_extra > 0:
            rows.append(f'<tr><td>🎭 Avatar / Figur</td><td>+ {avatar_extra} €</td></tr>')
    # 6. Form
    if form_extra > 0:
        rows.append(f'<tr><td>🔷 Form ({form_val.capitalize()})</td><td>+ {form_extra} €</td></tr>')
    # 7. Lieferung
    if liefer_extra > 0:
        rows.append(f'<tr><td>🚗 Lieferung (Umkreis)</td><td>+ {liefer_extra} €</td></tr>')

    table = (
        '<table class="price-calc-table">'
        '<tr class="section-header"><td colspan="2"><b>💰 Preisberechnung</b></td></tr>'
        + "".join(rows)
        + f'<tr class="total-row"><td><b>Gesamtpreis</b></td><td><b>{total} €</b></td></tr>'
        '</table>'
    )
    return table, f"{total} €"


def _make_styles():
    styles = getSampleStyleSheet()

    title = ParagraphStyle(
        "KidstorteTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=WEISS,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    subtitle = ParagraphStyle(
        "KidstorteSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=WEISS,
        alignment=TA_CENTER,
    )
    section = ParagraphStyle(
        "KidstorteSection",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=GREEN,
        spaceBefore=14,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "KidstorteBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#333333"),
        leading=14,
    )
    price_style = ParagraphStyle(
        "KidstortePrice",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=BRAUN,
        alignment=TA_RIGHT,
    )
    footer = ParagraphStyle(
        "KidstorteFooter",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=GRAU,
        alignment=TA_CENTER,
    )
    return {"title": title, "subtitle": subtitle, "section": section,
            "body": body, "price": price_style, "footer": footer}


def generate_order_pdf(order: dict, image_path: str | None = None) -> bytes:
    """
    Generiert ein PDF für eine Bestellung.
    order: Dict aus order_db.get_order() mit allen Feldern
    image_path: Relativer Pfad zum Vorschaubild (z.B. '/static/images/abc.png')
    Returns: PDF als bytes
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=2 * cm,
    )

    s = _make_styles()
    story = []

    # ── Header-Banner mit Logo (links) + Titel ────────
    # Wenn logo.png existiert: 2-Spalten-Layout, sonst nur Titel zentriert
    if LOGO_PATH.exists():
        try:
            logo = Image(str(LOGO_PATH), width=1.6 * cm, height=1.6 * cm,
                         kind="proportional")
            header_data = [[
                logo,
                Paragraph("Kidstorte", s["title"]),
            ]]
            header_table = Table(header_data,
                                 colWidths=[2.0 * cm, doc.width - 2.0 * cm])
        except Exception as e:
            logger.warning(f"Logo konnte nicht geladen werden: {e}")
            header_data = [[Paragraph("🎂 Kidstorte", s["title"])]]
            header_table = Table(header_data, colWidths=[doc.width])
    else:
        header_data = [[Paragraph("🎂 Kidstorte", s["title"])]]
        header_table = Table(header_data, colWidths=[doc.width])

    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAUN),
        ("ROUNDEDCORNERS", [6]),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(header_table)

    sub_data = [[Paragraph("Bestellbestätigung", s["subtitle"])]]
    sub_table = Table(sub_data, colWidths=[doc.width])
    sub_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAUN_HELL),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(sub_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── Bestellnummer & Datum ───────────────────────────
    order_id = order.get("id", "–")
    created = order.get("created_at", "")
    try:
        created_fmt = datetime.fromisoformat(str(created)).strftime("%d.%m.%Y %H:%M")
    except Exception:
        created_fmt = str(created)

    meta_data = [
        [Paragraph(f"<b>Bestellnummer:</b> #{order_id}", s["body"]),
         Paragraph(f"<b>Datum:</b> {created_fmt}", s["body"])],
    ]
    meta_table = Table(meta_data, colWidths=[doc.width / 2, doc.width / 2])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HELLGRAU),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Kundendaten ─────────────────────────────────────
    story.append(Paragraph("Kundendaten", s["section"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAUN_HELL, spaceAfter=6))

    customer_rows = [
        ["Name", order.get("customer_name", "–")],
        ["Adresse", f"{order.get('customer_street', '')},"
                    f" {order.get('customer_plz', '')} {order.get('customer_city', '')}"],
        ["Telefon", order.get("customer_phone", "–")],
        ["E-Mail", order.get("customer_email", "–")],
    ]
    cust_table = Table(
        [[Paragraph(f"<b>{k}</b>", s["body"]), Paragraph(v, s["body"])]
         for k, v in customer_rows],
        colWidths=[3.5 * cm, doc.width - 3.5 * cm],
    )
    cust_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#eeeeee")),
    ]))
    story.append(cust_table)
    story.append(Spacer(1, 0.3 * cm))

    # ── Bestelldetails ──────────────────────────────────
    story.append(Paragraph("Bestelldetails", s["section"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAUN_HELL, spaceAfter=6))

    order_info_raw = order.get("order_info", "{}")
    try:
        order_info = json.loads(order_info_raw) if isinstance(order_info_raw, str) else order_info_raw
    except Exception:
        order_info = {}

    labels = [
        ("anlass", "Anlass"), ("gaeste", "Gäste"), ("geschmack", "Geschmack"),
        ("form", "Form"), ("schichten", "Schichten"), ("fuellung", "Füllung"),
        ("dekoration", "Dekoration"), ("farbe", "Farbe"),
        ("allergien", "Allergien"), ("beschriftung", "Beschriftung"),
        ("abholung", "Abholung"), ("liefertermin", "Liefertermin"),
    ]

    detail_rows = []
    for key, label in labels:
        val = order_info.get(key) or order.get(key)
        if val and str(val).lower() not in ("keine", "n/a", ""):
            detail_rows.append([label, str(val)])

    if detail_rows:
        detail_table = Table(
            [[Paragraph(f"<b>{k}</b>", s["body"]), Paragraph(v, s["body"])]
             for k, v in detail_rows],
            colWidths=[3.5 * cm, doc.width - 3.5 * cm],
        )
        detail_table.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WEISS, HELLGRAU]),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#eeeeee")),
        ]))
        story.append(detail_table)

    # ── Preis ────────────────────────────────────────────
    # Zuerst den vom Chat berechneten Preis nutzen, nur als Fallback die Schätzung
    saved_price = (order.get("total_price") or "").strip()
    price_str = saved_price if saved_price else _estimate_price(order_info)
    if price_str:
        story.append(Spacer(1, 0.3 * cm))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAUN, spaceAfter=8))
        price_data = [[
            Paragraph("<b>Geschätzter Gesamtpreis:</b>", s["body"]),
            Paragraph(f"<b>{price_str}</b>", s["price"]),
        ]]
        price_table = Table(price_data, colWidths=[doc.width * 0.6, doc.width * 0.4])
        price_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BRAUN_BG),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("ROUNDEDCORNERS", [4]),
        ]))
        story.append(price_table)

    # ── Vorschaubild ─────────────────────────────────────
    if image_path:
        # image_path ist z.B. '/static/images/abc.png' → Datei relativ zum Projektroot
        img_file = Path(image_path.lstrip("/"))
        if img_file.exists():
            story.append(Spacer(1, 0.4 * cm))
            story.append(Paragraph("Vorschau Ihres Kuchens", s["section"]))
            story.append(HRFlowable(width="100%", thickness=1, color=BRAUN_HELL, spaceAfter=6))
            try:
                img = Image(str(img_file), width=10 * cm, height=10 * cm)
                img.hAlign = "CENTER"
                story.append(img)
                story.append(Spacer(1, 0.2 * cm))
                story.append(Paragraph(
                    "<i>Hinweis: Dies ist eine KI-generierte Vorschau. "
                    "Das fertige Produkt kann leicht abweichen.</i>",
                    s["body"]
                ))
            except Exception as e:
                logger.warning(f"Bild konnte nicht ins PDF eingebettet werden: {e}")

    story.append(Spacer(1, 0.5 * cm))

    # ── Hinweis ─────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=BRAUN_HELL, spaceAfter=8))
    story.append(Paragraph(
        "Wir melden uns in Kürze bei Ihnen zur Bestätigung. "
        "Bei Fragen erreichen Sie uns unter <b>0221-1234567</b>.",
        s["body"]
    ))
    story.append(Spacer(1, 1 * cm))

    # ── Footer ───────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRAU, spaceAfter=6))
    story.append(Paragraph(
        "Kidstorte Konditorei · Bäckerstraße 12, 50667 Köln · 0221-1234567",
        s["footer"]
    ))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


def save_order_pdf(order: dict, image_path: str | None = None) -> str:
    """
    Generiert PDF und speichert es unter static/pdfs/{order_id}.pdf.
    Returns: Relativer Pfad z.B. '/static/pdfs/42.pdf'
    """
    order_id = order.get("id")
    pdf_bytes = generate_order_pdf(order, image_path=image_path)
    path = PDF_DIR / f"{order_id}.pdf"
    path.write_bytes(pdf_bytes)
    logger.info(f"PDF gespeichert: {path}")
    return f"/static/pdfs/{order_id}.pdf"
