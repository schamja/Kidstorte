"""
Kidstorte – FastAPI Server mit Session-basiertem LangGraph Agent
"""
import asyncio
import os
import datetime
import time
import logging
from fastapi import FastAPI, Request, Response, HTTPException, Form, Body
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
from app.graph import CakeDreamsGraph
from services.session_manager import SessionManager
from app.config import ADMIN_PASSWORD, load_prompts_config, save_prompts_config
from monitoring.metrics import setup_logging, metrics
from services.cost_optimizer import response_cache, estimate_tokens, get_model_for_task
from monitoring.tracing import get_tracing_status, is_enabled as tracing_enabled
from services.order_db import (
    save_order, get_all_orders, update_order_status, get_order_stats,
    get_order, get_orders_per_day, get_available_dates, count_orders_on_date,
    save_rating, get_rating, get_all_ratings, get_rating_stats,
    delete_order,
)

# --- Logging (strukturiert JSON) ---
#Es schaltet das "Gehirn-Monitoring" ein
setup_logging(level="INFO", json_logs=False)
#Es ist deine interne "Blackbox", die alles mitschreibt, was im Kidstorte-Agenten
# passiert, damit du bei Fehlern genau weißt, wo du suchen musst.
logger = logging.getLogger("kidstorte")

# --- App ---
app = FastAPI(title="Cake Dreams Agent")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], #komminkation zwischen Backend und Frontend
    allow_methods=["*"], allow_headers=["*"]
)
# Bilder-speicher, statische Dateien & Ordner
Path("static/images").mkdir(parents=True, exist_ok=True)
Path("Bilder").mkdir(parents=True, exist_ok=True)
app.mount("/referenz", StaticFiles(directory="Bilder"), name="referenz")
app.mount("/static", StaticFiles(directory="static"), name="static")
#Jinja2 wird initialisert HTML mit echten daten befüllt
templates = Jinja2Templates(directory="templates")

# Casa Pastel (Chitré, Panamá): Konfigurator-API unter /api/casa
from app.casa_pastel import router as casa_router
app.include_router(casa_router)

# --- Shared Instances (stateless(vergesslich):bedeutet sie enthalten selbst
# keine Daten,sondern verarbeitet die state) die Werkzeuge---
graph = CakeDreamsGraph()
session_mgr = SessionManager()

# --- Jinja2 Filter + Startup ---
SESSION_COOKIE = "cake_session_id"

#1. Die "Hausmeister"-Funktionen (Setup & Session) räumt die alte Gespräche auf und breitet vor

@app.on_event("startup")
async def setup():
    import json as _json
    templates.env.filters["timestamp_format"] = (
        lambda ts: datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
        if ts else "N/A"
    )
    templates.env.filters["from_json"] = (
        lambda s: _json.loads(s) if s else {}
    )
    cleaned = session_mgr.cleanup_old_sessions()
    if cleaned:
        logger.info(f"Startup: {cleaned} alte Sessions aufgeräumt")

#Das Gedächnis, sie schaut nach cooki, wenn keine ist, erstellt neue SessionID,damit Ki weiss, neue Kunde
# --- Session Helper ---
def get_session_id(request: Request, response: Response) -> str:
    """Extrahiert oder erstellt session_id aus Cookie."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        session_id = session_mgr.create_session_id()
        response.set_cookie(
            key=SESSION_COOKIE, value=session_id,
            max_age=86400, httponly=True, samesite="lax"
        )
    return session_id


class ChatRequest(BaseModel):
    question: str

#2. Die Chat-Zentrale (Das Herzstück) Hier passiert die eigentliche Magie mit der KI.
# ==========================================
# CHAT ENDPOINTS
# ==========================================

# Casa Pastel ist zuerst nur unter /casa zu sehen. Mit CASA_PASTEL_AT_ROOT=1 in der .env
# wird sie zur Startseite (/), und die bisherige Kidstorte-Seite verschwindet.
CASA_PASTEL_AT_ROOT = os.getenv("CASA_PASTEL_AT_ROOT", "0") == "1"
_NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/")
def index():
    if CASA_PASTEL_AT_ROOT:
        return FileResponse("templates/index.html", headers=_NO_CACHE)
    return FileResponse("templates/kidstorte_chat.html", headers=_NO_CACHE)


@app.get("/casa")
def casa_pastel_page():
    """Casa-Pastel-Seite (Testadresse, solange sie noch nicht die Startseite ist)."""
    if CASA_PASTEL_AT_ROOT:
        return RedirectResponse("/", status_code=302)
    return FileResponse("templates/index.html", headers=_NO_CACHE)


@app.get("/chat")
def old_chat_page():
    """Frühere Kidstorte-Seite: läuft jetzt unter /; ist Casa Pastel die Startseite, geht es dorthin."""
    return RedirectResponse("/", status_code=302)


@app.post("/api/chat")
async def chat(request_body: ChatRequest, request: Request, response: Response):
    session_id = get_session_id(request, response)
    t_start = time.time()
    metrics.inc("chat.requests")

    try:
        question = request_body.question.strip()
        if not question:
            return JSONResponse(status_code=400, content={"detail": "Keine Frage"})

        # Session-State laden
        state = session_mgr.load_session(session_id)

        state["session_id"] = session_id

        # Graph durchlaufen (in Thread, damit Event-Loop nicht blockiert)
        state = await asyncio.to_thread(graph.run, state, question)

        # Klassischer Endpoint kann nicht streamen → Bild synchron nachgenerieren
        if state.get("_pending_image"):
            from app.nodes import generate_image
            state["_pending_image"] = False
            state = await asyncio.to_thread(generate_image, state)

        # Session-State speichern
        session_mgr.save_session(session_id, state)

        # Tokens tracken
        answer = state.get("response", "")
        model = get_model_for_task("generate")
        tokens_in = estimate_tokens(question)
        tokens_out = estimate_tokens(answer)
        metrics.record_tokens(tokens_in, tokens_out, model)
        metrics.inc("chat.success")

        return {
            "answer": answer,
            "image_url": state.get("image_url"),
            "image_url_cut": state.get("image_url_cut"),
            "reference_image_url": state.get("reference_image_url"),
            "intent": state.get("intent", ""),
            "order_info": state.get("order_info", {}),
            "order_complete": state.get("order_complete", False),
            "order_finalized": state.get("order_finalized", False),
            "show_address_form": state.get("show_address_form", False),
            "is_pickup": state.get("is_pickup", False),
            "question_todo": state.get("question_todo", {}),
            "current_field": state.get("current_field", ""),
        }

    except Exception as e:
        metrics.inc("chat.errors")
        metrics.record_error(str(e), "chat")
        logger.exception(f"Fehler im Chat-Endpoint: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut."}
        )
    finally:
        ms = (time.time() - t_start) * 1000
        metrics.record_latency("chat", ms)


@app.post("/api/reset-cache")
async def reset_cache(request: Request):
    """Löscht den Response-Cache (nur Admin)"""
    if request.cookies.get("admin_auth") != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Nicht autorisiert")
    response_cache._cache.clear()
    response_cache._timestamps.clear()
    return JSONResponse({"status": "ok", "message": "Cache geleert"})


@app.post("/api/chat/stream")
async def chat_stream(request: Request, request_body: ChatRequest):
    """
    Streaming Chat via SSE – nutzt den echten LangGraph!
    1. Graph läuft komplett durch (Intent, Extract, Nodes)
    2. Die fertige Antwort wird Wort-für-Wort gestreamt (Live-Tippen-Effekt)
    3. Bilder und Metadaten kommen als JSON-Events am Ende
    """
    from fastapi.responses import StreamingResponse
    import json as _json

    # Session-ID aus Cookie lesen oder neue erstellen
    # WICHTIG: Cookie wird direkt in StreamingResponse-Headers gesetzt,
    # weil FastAPI's response.set_cookie() bei StreamingResponse nicht funktioniert!
    session_id = request.cookies.get(SESSION_COOKIE)
    is_new_session = False
    if not session_id:
        session_id = session_mgr.create_session_id()
        is_new_session = True

    question = request_body.question.strip()
    if not question:
        return JSONResponse(status_code=400, content={"detail": "Keine Frage"})

    async def event_generator():
        try:
            # ── Phase 1: Graph durchlaufen (blockierend, aber in Thread) ──
            state = session_mgr.load_session(session_id)
            state["session_id"] = session_id
            yield f"data: {_json.dumps({'status': 'thinking'})}\n\n"

            state = await asyncio.to_thread(graph.run, state, question)
            session_mgr.save_session(session_id, state)

            answer = state.get("response", "")
            yield f"data: {_json.dumps({'status': 'streaming'})}\n\n"

            # ── Phase 2: Antwort Wort-für-Wort streamen (Live-Tippen) ──
            # Kein künstliches sleep mehr — der Graph braucht eh schon 1–3 s pro Turn.
            # Wörter werden so schnell rausgegeben wie der Browser sie rendert (= sofort).
            # Falls du den visuellen "Tipp-Effekt" zurück willst:
            #   await asyncio.sleep(0.005)  # 5 ms = kaum spürbar, sieht aber lebendig aus
            words = answer.split(" ")
            for i, word in enumerate(words):
                token = word if i == 0 else " " + word
                yield f"data: {_json.dumps({'token': token})}\n\n"

            # ── Phase 3: Metadaten als finales Event ──
            image_pending = bool(state.get("_pending_image"))
            meta = {
                "done": True,
                "image_url": state.get("image_url"),
                "image_url_cut": state.get("image_url_cut"),
                "reference_image_url": state.get("reference_image_url"),
                "image_pending": image_pending,
                "intent": state.get("intent", ""),
                "order_info": state.get("order_info", {}),
                "order_complete": state.get("order_complete", False),
                "order_finalized": state.get("order_finalized", False),
                "show_address_form": state.get("show_address_form", False),
                "is_pickup": state.get("is_pickup", False),
                "question_todo": state.get("question_todo", {}),
                "current_field": state.get("current_field", ""),
            }
            yield f"data: {_json.dumps(meta)}\n\n"

            # ── Phase 4: Bild parallel generieren (falls Graph es markiert hat) ──
            if image_pending:
                try:
                    from app.nodes import generate_image
                    state["_pending_image"] = False
                    state = await asyncio.to_thread(generate_image, state)
                    session_mgr.save_session(session_id, state)
                    img_event = {
                        "image_ready": True,
                        "image_url": state.get("image_url"),
                        "image_url_cut": state.get("image_url_cut"),
                        "reference_image_url": state.get("reference_image_url"),
                    }
                    yield f"data: {_json.dumps(img_event)}\n\n"
                except Exception as e:
                    logger.exception(f"Bildgenerierung (deferred) fehlgeschlagen: {e}")
                    err_event = {"image_ready": True, "image_url": None, "image_error": str(e)}
                    yield f"data: {_json.dumps(err_event)}\n\n"

        except Exception as e:
            logger.exception(f"Streaming-Fehler: {e}")
            yield f"data: {_json.dumps({'error': str(e)})}\n\n"

    # Cookie direkt in die StreamingResponse-Headers setzen
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    if is_new_session:
        from http.cookies import SimpleCookie
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE] = session_id
        cookie[SESSION_COOKIE]["max-age"] = "86400"
        cookie[SESSION_COOKIE]["httponly"] = True
        cookie[SESSION_COOKIE]["samesite"] = "Lax"
        cookie[SESSION_COOKIE]["path"] = "/"
        headers["Set-Cookie"] = cookie[SESSION_COOKIE].OutputString()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


@app.post("/api/generate-image")
async def gen_image(request_body: ChatRequest, request: Request, response: Response):
    """Generiert ein Bild basierend auf dem bisherigen Gespräch."""
    session_id = get_session_id(request, response)

    try:
        from app.nodes import generate_image
        state = session_mgr.load_session(session_id)
        state["user_input"] = request_body.question
        state = generate_image(state)

        # Antwort zum Verlauf hinzufügen und speichern
        state["messages"].append({"role": "assistant", "content": state["response"]})
        session_mgr.save_session(session_id, state)

        return {
            "answer": state.get("response", ""),
            "image_url": state.get("image_url"),
            "image_url_cut": state.get("image_url_cut"),
            "reference_image_url": state.get("reference_image_url"),
        }
    except Exception as e:
        logger.exception(f"Fehler bei Bildgenerierung: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/api/test-vision")
async def test_vision(dekoration: str = "Elsa", farbe: str = "blau", form: str = "rund", schichten: str = "3"):
    """Test-Endpunkt: Multimodale Referenzbild-Suche direkt testen."""
    from app.nodes import _find_best_reference
    order_info = {"dekoration": dekoration, "farbe": farbe, "form": form, "schichten": schichten}
    ref_url, explanation, detailed = _find_best_reference(order_info)
    return {
        "order_info": order_info,
        "reference_image_url": ref_url,
        "explanation": explanation,
        "detailed_description": detailed,
        "status": "match_found" if ref_url else "no_match",
    }


@app.post("/api/reset")
async def reset(request: Request, response: Response):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        session_mgr.delete_session(session_id)

    # Neue Session erstellen
    new_session_id = session_mgr.create_session_id()
    response.set_cookie(
        key=SESSION_COOKIE, value=new_session_id,
        max_age=86400, httponly=True, samesite="lax"
    )
    return {"message": "Gespräch zurückgesetzt"}


@app.get("/api/state")
async def get_state(request: Request, response: Response):
    """Debug: Zeigt den aktuellen Session-State."""
    session_id = get_session_id(request, response)
    state = session_mgr.load_session(session_id)
    return {
        "session_id": session_id[:12] + "...",
        "order_info": state.get("order_info", {}),
        "order_complete": state.get("order_complete", False),
        "intent": state.get("intent", ""),
        "message_count": len(state.get("messages", [])),
    }


# ==========================================
# ADMIN PANEL
# ==========================================

def verify_admin(request: Request):
    """Prüft Admin-Authentifizierung über Cookie."""
    if request.cookies.get("admin_auth") != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Nicht autorisiert")


@app.get("/admin/login")
async def admin_login_page(request: Request):
    return templates.TemplateResponse(request, "admin.html", {"request": request, "page": "login"})


@app.post("/admin/login")
async def admin_login(response: Response, password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        return HTMLResponse(
            "<script>alert('Falsches Passwort');history.back();</script>"
        )
    resp = JSONResponse(content={"redirect": "/admin"})
    resp.set_cookie(key="admin_auth", value=ADMIN_PASSWORD, max_age=3600, httponly=True)
    return resp


@app.get("/admin")
async def admin_dashboard(request: Request):
    verify_admin(request)

    config = load_prompts_config()
    stats = session_mgr.get_statistics()
    sessions = session_mgr.list_sessions()
    orders = get_all_orders()
    order_stats = get_order_stats()

    return templates.TemplateResponse(request, "admin.html", {
        "request": request,
        "page": "dashboard",
        "config": config,
        "stats": stats,
        "sessions": sessions,
        "orders": orders,
        "order_stats": order_stats,
    })


@app.post("/admin/prompts")
async def admin_save_prompts(request: Request):
    verify_admin(request)

    form_data = await request.form()
    config = load_prompts_config()

    # Prompts aus Formular aktualisieren
    for key in config.get("prompts", {}):
        form_key = f"prompt_{key}"
        if form_key in form_data:
            config["prompts"][key] = form_data[form_key]

    # Bot-Persönlichkeit aktualisieren
    if "bot_tone" in form_data:
        config["bot_personality"]["tone"] = form_data["bot_tone"]

    save_prompts_config(config)
    return JSONResponse(content={"status": "ok", "message": "Prompts gespeichert"})


@app.post("/admin/sessions/{session_id}/delete")
async def admin_delete_session(session_id: str, request: Request):
    verify_admin(request)
    session_mgr.delete_session(session_id)
    return JSONResponse(content={"status": "ok"})


@app.post("/admin/sessions/cleanup")
async def admin_cleanup_sessions(request: Request):
    verify_admin(request)
    count = session_mgr.cleanup_old_sessions()
    return JSONResponse(content={"status": "ok", "deleted": count})


@app.get("/admin/logout")
async def admin_logout():
    resp = JSONResponse(content={"redirect": "/admin/login"})
    resp.delete_cookie("admin_auth")
    return resp


@app.post("/api/chat/functions")
async def chat_with_tools(request: Request, body: dict = Body(...)):
    """Chat mit OpenAI Function Calling"""
    from function_calling import chat_with_functions
    from app.config import load_prompts_config

    session_id = request.cookies.get(SESSION_COOKIE) or session_mgr.create_session_id()
    state = session_mgr.load_session(session_id) or {}
    messages = state.get("messages", [])

    user_msg = body.get("message", "")
    messages.append({"role": "user", "content": user_msg})

    cfg = load_prompts_config()
    tone = cfg.get("bot_personality", {}).get("tone", "freundlich")
    system = f"Du bist ein {tone} Kuchenberater für Kidstorte. Nutze die verfügbaren Funktionen um Bestellungen zu erfassen und Preise zu berechnen."

    result = chat_with_functions(messages, system)
    messages.append({"role": "assistant", "content": result["response"]})
    state["messages"] = messages

    # Order updates in state übernehmen
    if result["order_updates"]:
        order_info = state.get("order_info", {})
        order_info.update(result["order_updates"])
        state["order_info"] = order_info

    session_mgr.save_session(session_id, state)

    return JSONResponse({
        "response": result["response"],
        "tool_calls": result["tool_calls"],
        "order_updates": result["order_updates"],
        "session_id": session_id,
    })


# ==========================================
# ORDER SUBMISSION
# ==========================================

class OrderSubmitRequest(BaseModel):
    name: str
    street: str
    plz: str
    city: str
    phone: str
    email: str


@app.post("/api/submit-order")
async def submit_order(request_body: OrderSubmitRequest, request: Request):
    """Speichert Kundendaten, sendet E-Mails an Designer und Kunden."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        return JSONResponse(status_code=400, content={"detail": "Keine Session gefunden"})

    # Aktuelle Bestelldaten aus Session laden
    state = session_mgr.load_session(session_id)
    order_info = state.get("order_info", {})

    # Preis: Chat-Preis bevorzugen, sonst mit _estimate_price berechnen
    chat_price = state.get("calculated_price", "")
    if not chat_price:
        try:
            from services.pdf_order import _estimate_price
            chat_price = _estimate_price(order_info) or ""
            logger.info(f"Kein Chat-Preis vorhanden, geschätzt: {chat_price}")
        except Exception:
            chat_price = ""

    customer_data = {
        "name": request_body.name.strip(),
        "email": request_body.email.strip(),
        "phone": request_body.phone.strip(),
        "street": request_body.street.strip(),
        "plz": request_body.plz.strip(),
        "city": request_body.city.strip(),
        "total_price": chat_price,
    }

    # Bestellung in SQLite speichern
    try:
        order_id = save_order(session_id, order_info, customer_data)
    except Exception as e:
        logger.exception(f"DB-Fehler beim Speichern der Bestellung: {e}")
        return JSONResponse(status_code=500, content={"detail": "Bestellung konnte nicht gespeichert werden."})

    # PDF generieren und speichern (mit Vorschaubild falls vorhanden)
    pdf_url = None
    try:
        from services.pdf_order import save_order_pdf
        full_order = get_order(order_id)
        if full_order:
            image_url = state.get("image_url") or state.get("last_image_url")
            pdf_url = save_order_pdf(full_order, image_path=image_url)
    except Exception as e:
        logger.warning(f"PDF-Generierung fehlgeschlagen: {e}")

    # E-Mails versenden (Fehler sind nicht kritisch)
    try:
        from services.email_service import send_order_email_with_pdf, send_order_email
        if pdf_url:
            from pathlib import Path
            pdf_bytes = Path(f"static/pdfs/{order_id}.pdf").read_bytes()
            send_order_email_with_pdf(order_info, customer_data, pdf_bytes, recipient_type="designer")
            send_order_email_with_pdf(order_info, customer_data, pdf_bytes, recipient_type="customer")
        else:
            send_order_email(order_info, customer_data, recipient_type="designer")
            send_order_email(order_info, customer_data, recipient_type="customer")
    except Exception as e:
        logger.warning(f"E-Mail-Versand fehlgeschlagen: {e}")

    # Session als vollständig abgeschlossen markieren
    state["show_address_form"] = False
    session_mgr.save_session(session_id, state)

    logger.info(f"Bestellung #{order_id} erfolgreich abgeschlossen")
    return {
        "status": "ok",
        "order_id": order_id,
        "pdf_url": pdf_url,
        "message": f"Vielen Dank, {request_body.name}! Ihre Bestellung #{order_id} wurde aufgenommen. Sie erhalten eine Bestätigung an {request_body.email}.",
    }


# ==========================================
# ADMIN – BESTELLUNGEN
# ==========================================

@app.get("/admin/orders")
async def admin_orders(request: Request):
    """Gibt alle Bestellungen als JSON zurück."""
    verify_admin(request)
    orders = get_all_orders()
    return JSONResponse({"orders": orders, "stats": get_order_stats()})


@app.post("/admin/orders/{order_id}/status")
async def admin_update_order_status(order_id: int, request: Request, body: dict = Body(...)):
    """Ändert den Status einer Bestellung. Bei 'fertig' → Bewertungseinladung."""
    verify_admin(request)
    status = body.get("status", "")
    ok = update_order_status(order_id, status)
    if not ok:
        raise HTTPException(status_code=400, detail="Ungültiger Status")

    if status == "fertig":
        try:
            from services.email_service import send_rating_invite
            order = get_order(order_id)
            if order:
                base_url = str(request.base_url).rstrip("/")
                send_rating_invite(order, base_url=base_url)
        except Exception as e:
            logger.warning(f"Bewertungseinladung fehlgeschlagen: {e}")

    return JSONResponse({"status": "ok"})


@app.delete("/admin/orders/{order_id}")
async def admin_delete_order(order_id: int, request: Request):
    """Löscht eine stornierte Bestellung endgültig."""
    verify_admin(request)
    ok = delete_order(order_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Nur stornierte Bestellungen können gelöscht werden")
    return JSONResponse({"status": "deleted"})


# ==========================================
# METRICS ENDPOINT
# ==========================================

@app.get("/api/tracing/status")
async def tracing_status(request: Request):
    """LangSmith Tracing-Status (Admin)."""
    from tracing import get_tracing_status
    return JSONResponse(get_tracing_status())


@app.get("/metrics")
async def get_metrics(request: Request):
    """Metriken-Endpunkt (nur Admin oder lokal)"""
    # Nur im lokalen Netz oder mit Admin-Cookie
    if request.cookies.get("admin_auth") != ADMIN_PASSWORD:
        client_ip = request.client.host if request.client else "unknown"
        if client_ip not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(status_code=401, detail="Nicht autorisiert")

    snapshot = metrics.snapshot()
    snapshot["cache"] = response_cache.stats()
    snapshot["tracing"] = get_tracing_status()
    return JSONResponse(snapshot)


# --- Database Diagram ---
@app.get("/database-diagram")
async def database_diagram():
    """Zeige ER-Diagramm der Datenstruktur"""
    return FileResponse("er-diagramm.html", media_type="text/html")


# ==========================================
# VERFÜGBARKEIT / KALENDER
# ==========================================

@app.get("/api/availability")
async def api_availability(month: str = ""):
    """Gibt Bestellanzahl pro Tag für einen Monat zurück."""
    if not month:
        import datetime
        month = datetime.date.today().strftime("%Y-%m")
    orders_per_day = get_orders_per_day(month)
    config = load_prompts_config()
    max_per_day = config.get("max_orders_per_day", 5)
    return JSONResponse({"month": month, "orders": orders_per_day, "max_per_day": max_per_day})


@app.get("/api/available-dates")
async def api_available_dates(days: int = 60):
    """Gibt Liste freier Lieferdaten zurück."""
    config = load_prompts_config()
    max_per_day = config.get("max_orders_per_day", 5)
    available = get_available_dates(days_ahead=days, max_per_day=max_per_day)
    return JSONResponse({"available": available, "max_per_day": max_per_day})


@app.get("/api/calendar/check")
async def api_calendar_check(date: str):
    """
    Prüft Verfügbarkeit für ein bestimmtes Datum.
    Nutzt cal.com wenn konfiguriert, sonst lokale DB.
    Query-Param: ?date=2026-03-25 oder ?date=25.03.2026
    """
    from services.cal_service import get_available_slots
    result = get_available_slots(date)
    return JSONResponse(result)


@app.get("/api/calendar/alternatives")
async def api_calendar_alternatives(date: str, days: int = 7):
    """
    Sucht alternative freie Termine rund um ein gewünschtes Datum.
    Query-Param: ?date=2026-03-25&days=7
    """
    from services.cal_service import get_alternative_dates
    alternatives = get_alternative_dates(date, days_range=days)
    return JSONResponse({"alternatives": alternatives})


@app.get("/api/calendar/status")
async def api_calendar_status():
    """Zeigt ob cal.com konfiguriert ist und welcher Modus aktiv ist."""
    from services.cal_service import is_configured, CAL_API_KEY, CAL_EVENT_TYPE_ID, CAL_USERNAME
    return JSONResponse({
        "calcom_configured": is_configured(),
        "has_api_key": bool(CAL_API_KEY),
        "event_type_id": CAL_EVENT_TYPE_ID or None,
        "username": CAL_USERNAME or None,
        "mode": "calcom" if is_configured() else "local",
    })


@app.post("/admin/capacity")
async def admin_set_capacity(request: Request, body: dict = Body(...)):
    """Setzt die maximale Bestellkapazität pro Tag."""
    verify_admin(request)
    max_per_day = int(body.get("max_per_day", 5))
    config = load_prompts_config()
    config["max_orders_per_day"] = max_per_day
    save_prompts_config(config)
    return JSONResponse({"status": "ok", "max_per_day": max_per_day})


# ==========================================
# PDF DOWNLOAD
# ==========================================

@app.get("/api/order-pdf/{order_id}")
async def get_order_pdf(order_id: int, request: Request):
    """Gibt die PDF-Bestellbestätigung zurück."""
    from pathlib import Path as _Path
    pdf_path = _Path(f"static/pdfs/{order_id}.pdf")

    # Zugriff: Admin oder Session die zu dieser Bestellung gehört
    is_admin = request.cookies.get("admin_auth") == ADMIN_PASSWORD
    order = get_order(order_id)
    session_id = request.cookies.get(SESSION_COOKIE)
    is_owner = order and order.get("session_id") == session_id

    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Kein Zugriff")

    if not pdf_path.exists():
        # PDF neu generieren falls nicht vorhanden
        if not order:
            raise HTTPException(status_code=404, detail="Bestellung nicht gefunden")
        try:
            from services.pdf_order import save_order_pdf
            save_order_pdf(order)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF-Fehler: {e}")

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"Bestellbestaetigung_#{order_id}.pdf",
    )


# ==========================================
# BEWERTUNGEN
# ==========================================

@app.get("/bewertung/{order_id}")
async def bewertung_page(order_id: int, request: Request):
    """Zeigt die Bewertungsseite für eine Bestellung."""
    order = get_order(order_id)
    if not order:
        return HTMLResponse("<h2>Bestellung nicht gefunden.</h2>", status_code=404)
    existing = get_rating(order_id)
    return templates.TemplateResponse(request, "bewertung.html", {
        "request": request,
        "order": order,
        "order_id": order_id,
        "already_rated": existing is not None,
        "existing_rating": existing,
    })


@app.post("/bewertung/{order_id}")
async def submit_bewertung(order_id: int, request: Request):
    """Speichert eine Bewertung."""
    form = await request.form()
    rating_val = form.get("rating")
    comment = form.get("comment", "").strip()

    if not rating_val or not rating_val.isdigit() or not (1 <= int(rating_val) <= 5):
        return HTMLResponse("<h2>Ungültige Bewertung.</h2>", status_code=400)

    order = get_order(order_id)
    if not order:
        return HTMLResponse("<h2>Bestellung nicht gefunden.</h2>", status_code=404)

    existing = get_rating(order_id)
    if existing:
        return templates.TemplateResponse(request, "bewertung.html", {
            "request": request,
            "order": order,
            "order_id": order_id,
            "already_rated": True,
            "existing_rating": existing,
        })

    save_rating(order_id, int(rating_val), comment)
    return templates.TemplateResponse(request, "bewertung.html", {
        "request": request,
        "order": order,
        "order_id": order_id,
        "already_rated": True,
        "submitted": True,
        "submitted_rating": int(rating_val),
        "existing_rating": None,
    })


@app.get("/admin/ratings")
async def admin_ratings(request: Request):
    """Gibt alle Bewertungen als JSON zurück."""
    verify_admin(request)
    ratings = get_all_ratings()
    stats = get_rating_stats()
    return JSONResponse({"ratings": ratings, "stats": stats})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
