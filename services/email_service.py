"""
Email Service – Versendet Bestell-E-Mails an Designer und Kunden.
SMTP-Konfiguration über .env-Variablen.
Falls SMTP nicht konfiguriert → nur loggen, kein Crash.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

logger = logging.getLogger("kidstorte")


def _get_smtp_config():
    """Lädt SMTP-Konfiguration aus config.py."""
    from app.config import (SMTP_HOST, SMTP_PORT, SMTP_USER,
                        SMTP_PASSWORD, DESIGNER_EMAIL, SHOP_NAME)
    return {
        "host": SMTP_HOST,
        "port": SMTP_PORT,
        "user": SMTP_USER,
        "password": SMTP_PASSWORD,
        "designer_email": DESIGNER_EMAIL,
        "shop_name": SHOP_NAME,
    }


def _is_configured(cfg: dict) -> bool:
    """Prüft ob SMTP konfiguriert ist."""
    return bool(cfg["host"] and cfg["user"] and cfg["password"])


def _build_order_html(order_data: dict, customer_data: dict, for_customer: bool = False) -> str:
    """Baut HTML-E-Mail mit Bestellübersicht."""
    order_info = order_data.get("order_info", {})
    shop_name = order_data.get("shop_name", "Kidstorte")

    labels = {
        "anlass": "Anlass", "gaeste": "Gäste", "geschmack": "Geschmack",
        "form": "Form", "schichten": "Schichten", "fuellung": "Füllung",
        "dekoration": "Dekoration", "farbe": "Farbe",
        "liefertermin": "Liefertermin",
    }

    rows = ""
    for key, label in labels.items():
        val = order_info.get(key)
        if val:
            rows += f"<tr><td style='padding:6px 12px;border-bottom:1px solid #eee;font-weight:600;'>{label}</td><td style='padding:6px 12px;border-bottom:1px solid #eee;'>{val}</td></tr>"

    customer_rows = f"""
    <tr><td style='padding:6px 12px;border-bottom:1px solid #eee;font-weight:600;'>Name</td><td style='padding:6px 12px;border-bottom:1px solid #eee;'>{customer_data.get('name', '-')}</td></tr>
    <tr><td style='padding:6px 12px;border-bottom:1px solid #eee;font-weight:600;'>Adresse</td><td style='padding:6px 12px;border-bottom:1px solid #eee;'>{customer_data.get('street', '-')}, {customer_data.get('plz', '')} {customer_data.get('city', '')}</td></tr>
    <tr><td style='padding:6px 12px;border-bottom:1px solid #eee;font-weight:600;'>Telefon</td><td style='padding:6px 12px;border-bottom:1px solid #eee;'>{customer_data.get('phone', '-')}</td></tr>
    <tr><td style='padding:6px 12px;border-bottom:1px solid #eee;font-weight:600;'>E-Mail</td><td style='padding:6px 12px;border-bottom:1px solid #eee;'>{customer_data.get('email', '-')}</td></tr>
    """

    if for_customer:
        greeting = f"<p>Vielen Dank für Ihre Bestellung bei {shop_name}!</p><p>Wir haben folgende Bestellung erhalten:</p>"
        footer = f"<p>Wir melden uns in Kürze bei Ihnen. Bei Fragen erreichen Sie uns unter 0221-1234567.</p><p>Herzliche Grüße,<br>Ihr {shop_name}-Team</p>"
    else:
        greeting = f"<p><strong>Neue Bestellung eingegangen!</strong></p>"
        footer = ""

    return f"""
    <div style="font-family: 'DM Sans', Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #e8b4a0, #d4956a); padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 24px;">{shop_name}</h1>
            <p style="color: white; margin: 4px 0 0; opacity: 0.9;">Bestellbestätigung</p>
        </div>
        <div style="padding: 24px; background: #fff; border: 1px solid #eee;">
            {greeting}
            <h3 style="margin-top: 20px; color: #5a3825;">Kundendaten</h3>
            <table style="width: 100%; border-collapse: collapse;">{customer_rows}</table>
            <h3 style="margin-top: 20px; color: #5a3825;">Bestelldetails</h3>
            <table style="width: 100%; border-collapse: collapse;">{rows}</table>
            {footer}
        </div>
        <div style="background: #f5f5f5; padding: 12px; text-align: center; border-radius: 0 0 8px 8px; font-size: 12px; color: #999;">
            {shop_name} Konditorei – Bäckerstraße 12, 50667 Köln
        </div>
    </div>
    """


def send_order_email(order_info: dict, customer_data: dict, recipient_type: str = "designer") -> bool:
    """
    Sendet Bestell-E-Mail.
    recipient_type: "designer" oder "customer"
    Returns: True bei Erfolg, False bei Fehler.
    """
    cfg = _get_smtp_config()

    if not _is_configured(cfg):
        logger.warning(f"SMTP nicht konfiguriert – E-Mail an {recipient_type} wird übersprungen")
        return False

    order_data = {"order_info": order_info, "shop_name": cfg["shop_name"]}

    if recipient_type == "customer":
        to_email = customer_data.get("email")
        if not to_email:
            logger.warning("Keine Kunden-E-Mail angegeben – überspringe")
            return False
        subject = f"Ihre Bestellung bei {cfg['shop_name']} – Bestätigung"
        html = _build_order_html(order_data, customer_data, for_customer=True)
    else:
        to_email = cfg["designer_email"]
        if not to_email:
            logger.warning("Keine Designer-E-Mail konfiguriert – überspringe")
            return False
        customer_name = customer_data.get("name", "Unbekannt")
        subject = f"Neue Bestellung von {customer_name}"
        html = _build_order_html(order_data, customer_data, for_customer=False)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["user"]
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)

        logger.info(f"E-Mail gesendet an {recipient_type}: {to_email}")
        return True

    except Exception as e:
        logger.error(f"E-Mail-Versand fehlgeschlagen ({recipient_type}): {e}")
        return False


def send_order_email_with_pdf(order_info: dict, customer_data: dict,
                               pdf_bytes: bytes, recipient_type: str = "customer") -> bool:
    """
    Sendet Bestell-E-Mail mit PDF-Anhang.
    """
    cfg = _get_smtp_config()
    if not _is_configured(cfg):
        logger.warning("SMTP nicht konfiguriert – E-Mail mit PDF wird übersprungen")
        return False

    order_data = {"order_info": order_info, "shop_name": cfg["shop_name"]}

    if recipient_type == "customer":
        to_email = customer_data.get("email")
        if not to_email:
            return False
        subject = f"Ihre Bestellung bei {cfg['shop_name']} – Bestätigung mit PDF"
        html = _build_order_html(order_data, customer_data, for_customer=True)
    else:
        to_email = cfg["designer_email"]
        if not to_email:
            return False
        subject = f"Neue Bestellung von {customer_data.get('name', 'Unbekannt')}"
        html = _build_order_html(order_data, customer_data, for_customer=False)

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = cfg["user"]
        msg["To"] = to_email

        # HTML-Teil
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt)

        # PDF-Anhang
        attachment = MIMEBase("application", "pdf")
        attachment.set_payload(pdf_bytes)
        encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition", "attachment",
            filename="Bestellbestaetigung_Kidstorte.pdf"
        )
        msg.attach(attachment)

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)

        logger.info(f"E-Mail mit PDF gesendet an {recipient_type}: {to_email}")
        return True

    except Exception as e:
        logger.error(f"E-Mail mit PDF fehlgeschlagen ({recipient_type}): {e}")
        return False


def send_rating_invite(order: dict, base_url: str = "") -> bool:
    """
    Schickt eine Bewertungseinladungs-E-Mail an den Kunden.
    """
    cfg = _get_smtp_config()
    if not _is_configured(cfg):
        logger.warning("SMTP nicht konfiguriert – Bewertungs-E-Mail wird übersprungen")
        return False

    to_email = order.get("customer_email")
    if not to_email:
        logger.warning("Keine Kunden-E-Mail für Bewertungseinladung")
        return False

    order_id = order.get("id")
    customer_name = order.get("customer_name", "Kunde")
    shop_name = cfg["shop_name"]
    rating_url = f"{base_url}/bewertung/{order_id}"

    html = f"""
    <div style="font-family: 'DM Sans', Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #e8b4a0, #d4956a); padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 24px;">{shop_name}</h1>
            <p style="color: white; margin: 4px 0 0; opacity: 0.9;">Wie war Ihr Kuchen?</p>
        </div>
        <div style="padding: 24px; background: #fff; border: 1px solid #eee;">
            <p>Liebe/r {customer_name},</p>
            <p>wir hoffen, Ihr Kuchen hat Ihnen und Ihren Gästen gut geschmeckt! 🎂</p>
            <p>Wir würden uns sehr freuen, wenn Sie sich einen Moment Zeit nehmen, um Ihre Bestellung zu bewerten.</p>
            <div style="text-align: center; margin: 24px 0;">
                <a href="{rating_url}"
                   style="background: #5a3825; color: white; padding: 12px 28px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 15px;">
                    ⭐ Jetzt bewerten
                </a>
            </div>
            <p style="color: #999; font-size: 12px;">Falls der Button nicht funktioniert, kopieren Sie diesen Link: {rating_url}</p>
        </div>
        <div style="background: #f5f5f5; padding: 12px; text-align: center; border-radius: 0 0 8px 8px; font-size: 12px; color: #999;">
            {shop_name} Konditorei – Bäckerstraße 12, 50667 Köln
        </div>
    </div>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Wie war Ihr Kuchen? – Bewertung für Bestellung #{order_id}"
        msg["From"] = cfg["user"]
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)

        logger.info(f"Bewertungseinladung gesendet an: {to_email}")
        return True

    except Exception as e:
        logger.error(f"Bewertungseinladung fehlgeschlagen: {e}")
        return False
