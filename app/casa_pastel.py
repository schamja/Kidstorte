"""
Casa Pastel – API für die neue Website (Chitré, Panamá).

Endpunkte:
  GET  /api/casa/config   → Größen, Sorten, Preise (aus static/casa-pastel/config.json)
  POST /api/casa/preview  → KI-Vorschaubild aus der Beschreibung des Kunden
  POST /api/casa/chat     → KI-Berater (LangGraph, app/casa_chat.py), nimmt keine Bestellungen an
  POST /api/casa/order    → Bestellung speichern (KEINE Online-Zahlung)

Der Preis wird hier auf dem Server noch einmal berechnet, damit niemand
im Browser einen anderen Preis mitschicken kann.
"""
import json
import time
import logging
from collections import defaultdict, deque
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.order_db import save_order

logger = logging.getLogger("kidstorte")
router = APIRouter(prefix="/api/casa", tags=["casa-pastel"])

CONFIG_PATH = Path("static/casa-pastel/config.json")


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _by_id(items: list, item_id: str) -> dict | None:
    return next((i for i in items if i["id"] == item_id), None)


def calculate_price(cfg: dict, sel: "CakeSelection") -> tuple[int, list[str]]:
    """Gibt (Preis in USD, Fehlerliste) zurück."""
    errors = []
    cake_type = _by_id(cfg["types"], sel.type)
    size = _by_id(cfg["sizes"], sel.size)
    if not cake_type:
        errors.append("type")
    if not size:
        errors.append("size")
    doughs = [_by_id(cfg["doughs"], d) for d in sel.doughs]
    if not (1 <= len(sel.doughs) <= 2) or None in doughs:
        errors.append("doughs")
    filling = _by_id(cfg["fillings"], sel.filling)
    if not filling:
        errors.append("filling")
    if errors:
        return 0, errors

    tiers = size["tiers"]
    base = cfg["prices"][cake_type["id"]][size["id"]]
    extras = (sum(d["extra"] for d in doughs) + filling["extra"]) * tiers
    return base + extras, []


# ── Einfaches Limit für KI-Bilder (Kostenschutz) ─────────────────────────
_preview_hits: dict[str, deque] = defaultdict(deque)


def _allow_preview(client_key: str, limit: int) -> bool:
    now = time.time()
    hits = _preview_hits[client_key]
    while hits and now - hits[0] > 3600:
        hits.popleft()
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True


# ── Modelle ──────────────────────────────────────────────────────────────
class CakeSelection(BaseModel):
    type: str
    size: str
    doughs: list[str] = Field(default_factory=list)
    filling: str


class PreviewRequest(BaseModel):
    description: str = Field(min_length=5, max_length=600)
    selection: CakeSelection | None = None


class ChatTurn(BaseModel):
    role: str
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=600)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    lang: str = "es"


class OrderRequest(BaseModel):
    selection: CakeSelection
    design: str = Field(default="", max_length=1000)
    preview_url: str = ""
    name: str = Field(min_length=2, max_length=80)
    whatsapp: str = Field(min_length=7, max_length=25)
    email: str = Field(min_length=5, max_length=120)
    pickup_date: str
    notes: str = Field(default="", max_length=600)
    lang: str = "es"


# ── Endpunkte ────────────────────────────────────────────────────────────
@router.get("/config")
def get_config():
    return load_config()


GALLERY_DIR = Path("static/casa-pastel/galeria")


def _post_date(f: Path) -> str:
    """Datum des Instagram-Beitrags aus dem Dateinamen (instagram_JJJJMMTThhmm.jpg).
    Ohne Datum im Namen zählt das Änderungsdatum der Datei."""
    import re
    from datetime import datetime
    m = re.search(r"(\d{8,12})", f.stem)
    if m:
        return m.group(1).ljust(12, "0")
    return datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y%m%d%H%M")


@router.get("/gallery")
def gallery():
    """Fotos aus static/casa-pastel/galeria/ (einfach Bilder dort hineinlegen)."""
    if not GALLERY_DIR.exists():
        return {"images": []}
    files = sorted(
        (f for f in GALLERY_DIR.iterdir() if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}),
        key=_post_date, reverse=True,
    )
    return {"images": [f"/static/casa-pastel/galeria/{f.name}" for f in files[:12]]}


_DESIGN_SYSTEM = (
    "You write prompts for an image generator. The image shows ONE celebration cake from a small artisan bakery. "
    "The customer's wish can be in Spanish, English or German. Translate it into English and keep EVERY element "
    "the customer asks for, especially decorations on or around the cake: figures and toppers (for example a "
    "football player, dolls, animals, cartoon-style characters, a princess), a 2D avatar or photo of a person "
    "(show it as a flat edible printed image on the cake), doll cakes (a doll whose dress or skirt is the cake), "
    "sports, hobbies, colors, flowers, number of tiers. Show all figures as handmade edible decorations "
    "(fondant or sugar-paste figures, or edible print). "
    "Include ONLY what the customer asked for plus the cake style: do not invent extra figures, photo prints, "
    "numbers or objects. "
    "Replace names of real people, clubs, brands, toys or copyrighted characters (for example Messi, Real Madrid, "
    "Barbie, Disney, Paw Patrol) with a neutral visual description of the look (for example: 'a football player "
    "figure in a blue and garnet striped jersey', 'two fashion doll figures'), so the image can be made. "
    "Never add written words, names or letters on the cake. Reply with the prompt only, at most 90 words."
)


def _design_prompt(description: str, details: str) -> str:
    """Kundenwunsch (ES/EN/DE) → englischer Bild-Prompt, der Figuren, Avatare, Puppen usw. behält."""
    wish = f'Customer\'s wish: "{description}".{details}'
    try:
        from app.nodes import _llm_chat
        wish = _llm_chat(
            [{"role": "system", "content": _DESIGN_SYSTEM},
             {"role": "user", "content": description + details}],
            temperature=0.2, max_tokens=220,
        ).strip().strip('"')
    except Exception as e:  # ohne Übersetzung weiter, Bild klappt meist trotzdem
        logger.warning(f"Casa Pastel: Design-Prompt konnte nicht aufbereitet werden: {e}")
    return (
        "Professional product photo of a single handmade celebration cake from a small artisan bakery. "
        f"{wish} "
        "Show the whole cake with all its decorations and figures, centered on a cake stand, soft natural light, "
        "light cream background, photorealistic, appetizing. No written text, no lettering, no watermark."
    )


@router.post("/preview")
def preview(body: PreviewRequest, request: Request):
    cfg = load_config()
    client = request.client.host if request.client else "unknown"
    if not _allow_preview(client, int(cfg.get("preview_limit_per_hour", 5))):
        return JSONResponse(status_code=429, content={"error": "limit"})

    details = ""
    if body.selection:
        t = _by_id(cfg["types"], body.selection.type)
        s = _by_id(cfg["sizes"], body.selection.size)
        if t:
            details += f" Cake style: {t['name']['en']}."
        if s:
            details += f" {'Two-tier' if s['tiers'] == 2 else 'Single-tier'} round cake."

    prompt = _design_prompt(body.description.strip(), details)
    try:
        from app.nodes import _generate_openai
        url = _generate_openai(prompt, "casa-pastel")
        return {"image_url": url}
    except Exception as e:
        logger.exception(f"Casa Pastel Vorschau fehlgeschlagen: {e}")
        return JSONResponse(status_code=503, content={"error": "image"})


_chat_hits: dict[str, deque] = defaultdict(deque)


@router.post("/chat")
def chat(body: ChatRequest, request: Request):
    """KI-Berater: beantwortet Fragen, nimmt aber keine Bestellungen an."""
    cfg = load_config()
    client = request.client.host if request.client else "unknown"
    hits, now = _chat_hits[client], time.time()
    while hits and now - hits[0] > 3600:
        hits.popleft()
    if len(hits) >= int(cfg.get("chat_limit_per_hour", 40)):
        return JSONResponse(status_code=429, content={"error": "limit"})
    hits.append(now)

    lang = body.lang if body.lang in ("es", "en", "de") else "es"
    try:
        from app.casa_chat import run_chat
        reply = run_chat(cfg, body.message, [t.model_dump() for t in body.history], lang)
        return {"reply": reply}
    except Exception as e:
        logger.exception(f"Casa Pastel Chat fehlgeschlagen: {e}")
        return JSONResponse(status_code=503, content={"error": "chat"})


@router.post("/order")
def order(body: OrderRequest, request: Request):
    cfg = load_config()
    price, errors = calculate_price(cfg, body.selection)

    phone = "".join(c for c in body.whatsapp if c.isdigit() or c == "+")
    if len(phone.replace("+", "")) < 7:
        errors.append("whatsapp")

    import re
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", body.email.strip()):
        errors.append("email")

    try:
        pickup = date.fromisoformat(body.pickup_date)
        if pickup < date.today() + timedelta(days=int(cfg.get("min_lead_days", 3))):
            errors.append("pickup_date")
    except ValueError:
        errors.append("pickup_date")

    if errors:
        return JSONResponse(status_code=400, content={"error": "invalid", "fields": errors})

    lang = body.lang if body.lang in ("es", "en", "de") else "es"
    t = _by_id(cfg["types"], body.selection.type)
    s = _by_id(cfg["sizes"], body.selection.size)
    doughs = [_by_id(cfg["doughs"], d)["name"][lang] for d in body.selection.doughs]
    f = _by_id(cfg["fillings"], body.selection.filling)
    deposit = round(price * cfg.get("deposit_percent", 50) / 100, 2)

    # Preispositionen für die Rechnung (gleiche Rechnung wie calculate_price)
    tiers = s["tiers"]
    positions = [{"kind": "base", "text": f"{t['name'][lang]} · {s['name'][lang]}",
                  "usd": cfg["prices"][t["id"]][s["id"]]}]
    for d in body.selection.doughs:
        dd = _by_id(cfg["doughs"], d)
        positions.append({"kind": "dough", "text": dd["name"][lang], "unit": dd["extra"],
                          "tiers": tiers, "usd": dd["extra"] * tiers})
    positions.append({"kind": "filling", "text": f["name"][lang], "unit": f["extra"],
                      "tiers": tiers, "usd": f["extra"] * tiers})

    # Schlüssel auf Deutsch, damit der bestehende Admin-Bereich sie lesbar anzeigt
    order_info = {
        "art": t["name"][lang],
        "groesse": s["name"][lang],
        "etagen": s["tiers"],
        "schichten": f"{cfg.get('layers_per_tier', 4)} pro Etage",
        "geschmack": " / ".join(doughs),
        "fuellung": f["name"][lang],
        "design": body.design.strip(),
        "vorschau": body.preview_url if body.preview_url.startswith("/static/images/") else "",
        "notizen": body.notes.strip(),
        "abholung": body.pickup_date,
        "liefertermin": body.pickup_date,
        "anzahlung": f"${deposit:.2f} (50 %)",
        "preis_usd": price,
        "positionen": positions,
        "anzahlung_usd": deposit,
        "sprache": lang,
        "quelle": "Casa Pastel Website",
    }
    customer = {
        "name": body.name.strip(),
        "email": body.email.strip(),
        "phone": phone,
        "street": "",
        "plz": "",
        "city": "Chitré",
        "total_price": f"${price:.2f}",
    }
    session_id = request.cookies.get("cake_session_id") or f"casa-{int(time.time())}"
    try:
        order_id = save_order(session_id, order_info, customer)
    except Exception as e:
        logger.exception(f"Casa Pastel Bestellung fehlgeschlagen: {e}")
        return JSONResponse(status_code=500, content={"error": "save"})

    logger.info(f"Casa Pastel Bestellung #{order_id}: {t['id']} {s['id']} ${price}")
    # Bestellbestätigung als PDF per E-Mail (im Hintergrund, die Antwort wartet nicht darauf)
    from app.casa_invoice import send_document_async
    send_document_async(order_id, "confirmation")
    return {"order_id": order_id, "price": price, "deposit": deposit}
