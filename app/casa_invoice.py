"""
Casa Pastel – Bestellbestätigung und Rechnung als PDF, Versand per E-Mail.

Zwei Dokumente (in der Sprache der Bestellung: es / en / de):
  "confirmation"  sofort nach der Anfrage – noch nichts zu zahlen
  "invoice"       wenn die Bestellung im Admin angenommen wird
                  (Status "in_bearbeitung") – 50 % Anzahlung fällig

Ohne Steuer: Preise sind Endpreise. SMTP-Zugang kommt aus der .env
(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD); eine Kopie geht an
DESIGNER_EMAIL. Ist SMTP nicht eingerichtet, wird nur geloggt.
"""
import io
import json
import logging
import re
import smtplib
import threading
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape
from pathlib import Path

logger = logging.getLogger("kidstorte")

LOGO = Path("static/casa-pastel/logo-600.jpg")
CONFIG = Path("static/casa-pastel/config.json")

TXT = {
    "es": {
        "confirmation": "Confirmación de pedido", "invoice": "Factura",
        "number": "N.º", "date": "Fecha", "pickup": "Recogida", "customer": "Cliente",
        "item": "Descripción", "amount": "Importe",
        "type": "Tipo", "size": "Tamaño", "tiers": "Pisos", "dough": "Masa", "filling": "Relleno",
        "design": "Diseño", "notes": "Comentarios",
        "total": "Total", "deposit": "Anticipo 50 %", "rest": "Resto al recoger",
        "included": "incluido", "per_tier": "por piso", "tier1": "piso", "tierN": "pisos",
        "base": "Pastel", "extra_dough": "Masa", "extra_filling": "Relleno", "details": "Detalles",
        "note_confirmation": "Esto es la confirmación de tu solicitud, todavía no es una factura. "
                             "No pagas nada ahora: revisamos tu pedido y te contactamos por WhatsApp.",
        "note_invoice": "¡Tu pedido fue aceptado! Por favor paga el anticipo del 50 % ({dep}). "
                        "El resto ({rest}) se paga al recoger el pastel en Chitré. "
                        "Coordinamos el pago contigo por WhatsApp.",
        "prices": "Precios en dólares (USD), sin impuestos adicionales.",
        "thanks": "¡Gracias por elegir Casa Pastel!",
        "subject_confirmation": "Casa Pastel – Confirmación de tu pedido #{id}",
        "subject_invoice": "Casa Pastel – Factura de tu pedido #{id}",
        "hello": "Hola {name},",
        "mail_confirmation": "gracias por tu solicitud. En el PDF adjunto está el resumen de tu pedido #{id}. "
                             "Todavía no pagas nada: revisamos tu pedido y te escribimos por WhatsApp.",
        "mail_invoice": "¡tu pedido #{id} fue aceptado! En el PDF adjunto está tu factura. "
                        "Anticipo (50 %): {dep}. Resto al recoger: {rest}.",
        "bye": "Saludos dulces,", "file_confirmation": "Confirmacion", "file_invoice": "Factura",
    },
    "en": {
        "confirmation": "Order confirmation", "invoice": "Invoice",
        "number": "No.", "date": "Date", "pickup": "Pickup", "customer": "Customer",
        "item": "Description", "amount": "Amount",
        "type": "Type", "size": "Size", "tiers": "Tiers", "dough": "Sponge", "filling": "Filling",
        "design": "Design", "notes": "Comments",
        "total": "Total", "deposit": "50 % deposit", "rest": "Balance at pickup",
        "included": "included", "per_tier": "per tier", "tier1": "tier", "tierN": "tiers",
        "base": "Cake", "extra_dough": "Sponge", "extra_filling": "Filling", "details": "Details",
        "note_confirmation": "This confirms your request; it is not an invoice yet. "
                             "You pay nothing now: we review your order and contact you on WhatsApp.",
        "note_invoice": "Your order has been accepted! Please pay the 50 % deposit ({dep}). "
                        "The balance ({rest}) is paid when you pick up the cake in Chitré. "
                        "We arrange the payment with you on WhatsApp.",
        "prices": "Prices in US dollars (USD), no additional taxes.",
        "thanks": "Thank you for choosing Casa Pastel!",
        "subject_confirmation": "Casa Pastel – Confirmation of your order #{id}",
        "subject_invoice": "Casa Pastel – Invoice for your order #{id}",
        "hello": "Hi {name},",
        "mail_confirmation": "thank you for your request. The attached PDF summarises your order #{id}. "
                             "You don't pay anything yet: we review your order and message you on WhatsApp.",
        "mail_invoice": "your order #{id} has been accepted! Your invoice is attached. "
                        "Deposit (50 %): {dep}. Balance at pickup: {rest}.",
        "bye": "Sweet regards,", "file_confirmation": "Confirmation", "file_invoice": "Invoice",
    },
    "de": {
        "confirmation": "Bestellbestätigung", "invoice": "Rechnung",
        "number": "Nr.", "date": "Datum", "pickup": "Abholung", "customer": "Kunde",
        "item": "Beschreibung", "amount": "Betrag",
        "type": "Art", "size": "Größe", "tiers": "Etagen", "dough": "Teig", "filling": "Füllung",
        "design": "Design", "notes": "Anmerkungen",
        "total": "Gesamt", "deposit": "Anzahlung 50 %", "rest": "Rest bei Abholung",
        "included": "inklusive", "per_tier": "pro Etage", "tier1": "Etage", "tierN": "Etagen",
        "base": "Torte", "extra_dough": "Teig", "extra_filling": "Füllung", "details": "Details",
        "note_confirmation": "Dies ist die Bestätigung deiner Anfrage, noch keine Rechnung. "
                             "Du zahlst jetzt nichts: Wir prüfen deine Bestellung und melden uns per WhatsApp.",
        "note_invoice": "Deine Bestellung wurde angenommen! Bitte zahle die Anzahlung von 50 % ({dep}). "
                        "Der Rest ({rest}) wird bei der Abholung der Torte in Chitré bezahlt. "
                        "Die Zahlung besprechen wir mit dir per WhatsApp.",
        "prices": "Preise in US-Dollar (USD), ohne zusätzliche Steuern.",
        "thanks": "Danke, dass du dich für Casa Pastel entschieden hast!",
        "subject_confirmation": "Casa Pastel – Bestätigung deiner Bestellung #{id}",
        "subject_invoice": "Casa Pastel – Rechnung zu deiner Bestellung #{id}",
        "hello": "Hallo {name},",
        "mail_confirmation": "danke für deine Anfrage. Im PDF-Anhang findest du die Übersicht deiner Bestellung #{id}. "
                             "Du zahlst noch nichts: Wir prüfen deine Bestellung und schreiben dir per WhatsApp.",
        "mail_invoice": "deine Bestellung #{id} wurde angenommen! Im Anhang findest du deine Rechnung. "
                        "Anzahlung (50 %): {dep}. Rest bei Abholung: {rest}.",
        "bye": "Süße Grüße,", "file_confirmation": "Bestellbestaetigung", "file_invoice": "Rechnung",
    },
}


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _order_values(order: dict) -> dict:
    """Liest Bestelldaten aus dem DB-Eintrag (order_info ist JSON)."""
    info = order.get("order_info") or {}
    if isinstance(info, str):
        try:
            info = json.loads(info)
        except ValueError:
            info = {}
    lang = info.get("sprache") if info.get("sprache") in TXT else "es"
    total = info.get("preis_usd")
    if total is None:  # ältere Bestellungen: aus "total_price" ("$65.00") lesen
        m = re.search(r"[\d.,]+", str(order.get("total_price", "")).replace(",", ""))
        total = float(m.group()) if m else 0.0
    total = float(total)
    deposit = float(info.get("anzahlung_usd", round(total / 2, 2)))
    return {"info": info, "lang": lang, "total": total, "deposit": deposit, "rest": round(total - deposit, 2)}


def is_casa_order(order: dict) -> bool:
    return "Casa Pastel" in str(order.get("order_info", ""))


def build_pdf(order: dict, kind: str) -> bytes:
    """Erstellt Bestellbestätigung (kind="confirmation") oder Rechnung (kind="invoice")."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    v = _order_values(order)
    t, info = TXT[v["lang"]], v["info"]
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    PINK, MINT, MINT_D, INK = (colors.HexColor(c) for c in ("#DC7F97", "#B5DCC8", "#3D7A63", "#3E3933"))
    CREAM, LINE, MUTED = (colors.HexColor(c) for c in ("#FBF7F1", "#E2D6C4", "#7B7166"))

    st = lambda name, **kw: ParagraphStyle(name, fontName=kw.pop("font", "Helvetica"), textColor=kw.pop("color", INK), **kw)
    S = {
        "title": st("t", font="Helvetica-Bold", fontSize=20, leading=24, color=PINK),
        "meta": st("m", fontSize=9.5, leading=13, color=MUTED),
        "h": st("h", font="Helvetica-Bold", fontSize=10.5, leading=14, color=MINT_D),
        "body": st("b", fontSize=10, leading=14),
        "small": st("s", fontSize=8.5, leading=12, color=MUTED),
        "note": st("n", fontSize=10, leading=14, color=INK),
    }
    created = str(order.get("created_at") or "")[:10] or datetime.now().strftime("%Y-%m-%d")
    number = f"CP-{int(order['id']):04d}"

    logo = Image(str(LOGO), 30 * mm, 30 * mm) if LOGO.exists() else Paragraph("Casa Pastel", S["title"])
    head_right = [
        Paragraph(t[kind], S["title"]),
        Paragraph(f"{t['number']} {number} · {t['date']} {created}", S["meta"]),
        Paragraph(f"Casa Pastel · Chitré, Herrera · Panamá · WhatsApp +{cfg.get('whatsapp_business', '')}", S["meta"]),
    ]
    head = Table([[logo, head_right]], colWidths=[36 * mm, None])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    cust = [Paragraph(t["customer"], S["h"]),
            Paragraph(escape(order.get("customer_name") or ""), S["body"]),
            Paragraph(f"WhatsApp: {escape(order.get('customer_phone') or '')}", S["body"]),
            Paragraph(escape(order.get("customer_email") or ""), S["body"])]
    pick = [Paragraph(t["pickup"], S["h"]), Paragraph(escape(str(info.get("abholung", ""))), S["body"]),
            Paragraph("Chitré", S["body"])]
    who = Table([[cust, pick]], colWidths=[100 * mm, None])
    who.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    R = lambda txt: Paragraph(txt, ParagraphStyle("r", parent=S["body"], alignment=2))
    rows = [[Paragraph(f"<b>{t['item']}</b>", S["body"]), R(f"<b>{t['amount']}</b>")]]
    positions = info.get("positionen")
    if positions:  # jede Preisposition einzeln
        label = {"base": t["base"], "dough": t["extra_dough"], "filling": t["extra_filling"]}
        for pos in positions:
            txt = f"<b>{escape(label.get(pos.get('kind'), ''))}:</b> {escape(str(pos.get('text', '')))}"
            if pos.get("kind") != "base" and pos.get("unit"):
                n = int(pos.get("tiers") or 1)
                txt += f" <font color='#7B7166'>(+{_money(pos['unit'])} {t['per_tier']} × {n} {t['tier1'] if n == 1 else t['tierN']})</font>"
            amount = _money(pos["usd"]) if pos.get("usd") else t["included"]
            rows.append([Paragraph(txt, S["body"]), R(amount)])
        extra = [(t["design"], info.get("design")), (t["notes"], info.get("notizen"))]
        extra_txt = "<br/>".join(f"<b>{escape(k)}:</b> {escape(str(val))}" for k, val in extra if val)
        if extra_txt:
            rows.append([Paragraph(extra_txt, S["small"]), ""])
    else:  # ältere Bestellungen ohne Positionen: eine Zeile mit Gesamtbetrag
        desc = [(t["type"], info.get("art")), (t["size"], info.get("groesse")), (t["dough"], info.get("geschmack")),
                (t["filling"], info.get("fuellung")), (t["design"], info.get("design")), (t["notes"], info.get("notizen"))]
        text = "<br/>".join(f"<b>{escape(k)}:</b> {escape(str(val))}" for k, val in desc if val)
        rows.append([Paragraph(text, S["body"]), R(_money(v["total"]))])
    W = [140 * mm, 34 * mm]  # Seitenbreite 210 mm minus Ränder
    items = Table(rows, colWidths=W)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), MINT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -1), 0.6, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    sums = Table([
        [t["total"], _money(v["total"])],
        [t["deposit"], _money(v["deposit"])],
        [t["rest"], _money(v["rest"])],
    ], colWidths=W)
    sums.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("FONTNAME", (0, 1 if kind == "invoice" else 0), (-1, 1 if kind == "invoice" else 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1 if kind == "invoice" else 0), (-1, 1 if kind == "invoice" else 0), colors.HexColor("#FBE5EB")),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    note_txt = t["note_confirmation"] if kind == "confirmation" else t["note_invoice"].format(
        dep=_money(v["deposit"]), rest=_money(v["rest"]))
    note = Table([[Paragraph(note_txt, S["note"])]], colWidths=[sum(W)])
    note.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CREAM), ("BOX", (0, 0), (-1, -1), 0.8, PINK),
                              ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                              ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10)]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Casa Pastel – {t[kind]} {number}", author="Casa Pastel")
    doc.build([head, Spacer(1, 8 * mm), who, Spacer(1, 7 * mm), items, Spacer(1, 2 * mm), sums,
               Spacer(1, 7 * mm), note, Spacer(1, 5 * mm), Paragraph(t["prices"], S["small"]),
               Spacer(1, 3 * mm), Paragraph(t["thanks"], S["h"])])
    return buf.getvalue()


def _mail_html(t: dict, text: str, name: str) -> str:
    return (
        '<div style="font-family:Arial,sans-serif;background:#F3EADD;padding:24px">'
        '<div style="max-width:560px;margin:0 auto;background:#FBF7F1;border:3px solid #EFB1C0;border-radius:16px;padding:24px;color:#3E3933">'
        '<h2 style="margin:0 0 12px;color:#DC7F97;font-family:Georgia,serif">Casa Pastel</h2>'
        f'<p>{escape(t["hello"].format(name=name))}</p><p>{escape(text)}</p>'
        f'<p style="margin-top:20px">{escape(t["bye"])}<br>Casa Pastel · Chitré, Panamá</p></div></div>'
    )


def send_document(order: dict, kind: str) -> bool:
    """Schickt Bestätigung/Rechnung als PDF an die Kundin bzw. den Kunden (Kopie an den Shop)."""
    from services.email_service import _get_smtp_config, _is_configured
    smtp = _get_smtp_config()
    to = (order.get("customer_email") or "").strip()
    if not _is_configured(smtp):
        logger.warning(f"Casa Pastel: SMTP nicht eingerichtet – {kind} für #{order.get('id')} nicht gesendet")
        return False
    if not to:
        logger.warning(f"Casa Pastel: keine E-Mail-Adresse bei #{order.get('id')} – {kind} nicht gesendet")
        return False

    v = _order_values(order)
    t = TXT[v["lang"]]
    oid = order["id"]
    name = (order.get("customer_name") or "").split(" ")[0] or "🙂"
    text = (t["mail_confirmation"] if kind == "confirmation" else t["mail_invoice"]).format(
        id=oid, dep=_money(v["deposit"]), rest=_money(v["rest"]))
    try:
        pdf = build_pdf(order, kind)
        msg = MIMEMultipart("mixed")
        msg["Subject"] = t[f"subject_{kind}"].format(id=oid)
        msg["From"] = formataddr(("Casa Pastel", smtp["user"]))
        msg["To"] = to
        if smtp.get("designer_email"):
            msg["Bcc"] = smtp["designer_email"]
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(f"{t['hello'].format(name=name)}\n\n{text}\n\n{t['bye']}\nCasa Pastel · Chitré, Panamá", "plain", "utf-8"))
        alt.attach(MIMEText(_mail_html(t, text, name), "html", "utf-8"))
        msg.attach(alt)
        att = MIMEApplication(pdf, _subtype="pdf")
        att.add_header("Content-Disposition", "attachment", filename=f"CasaPastel_{t['file_' + kind]}_CP-{int(oid):04d}.pdf")
        msg.attach(att)

        port = int(smtp["port"] or 587)
        server = smtplib.SMTP_SSL(smtp["host"], port, timeout=30) if port == 465 else smtplib.SMTP(smtp["host"], port, timeout=30)
        with server:
            if port != 465:
                server.starttls()
            server.login(smtp["user"], smtp["password"])
            server.send_message(msg)
        logger.info(f"Casa Pastel: {kind} für #{oid} gesendet")
        return True
    except Exception as e:
        logger.error(f"Casa Pastel: {kind} für #{oid} fehlgeschlagen: {e}")
        return False


def send_document_async(order_id: int, kind: str) -> None:
    """Versand im Hintergrund, damit die Bestellung nicht auf den Mailserver warten muss."""
    def run():
        from services.order_db import get_order
        order = get_order(order_id)
        if order:
            send_document(order, kind)
    threading.Thread(target=run, daemon=True).start()
