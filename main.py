"""
Kidstorte – FastAPI Server mit Session-basiertem LangGraph Agent
"""
import datetime
import time
import logging
from fastapi import FastAPI, Request, Response, HTTPException, Form, Body
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
from graph import CakeDreamsGraph
from session_manager import SessionManager
from config import ADMIN_PASSWORD, load_prompts_config, save_prompts_config
from monitoring import setup_logging, metrics
from cost_optimizer import response_cache, estimate_tokens, get_model_for_task

# --- Logging (strukturiert JSON) ---
setup_logging(level="INFO", json_logs=False)
logger = logging.getLogger("kidstorte")

# --- App ---
app = FastAPI(title="Cake Dreams Agent")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"]
)
Path("static/images").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# --- Shared Instances (stateless) ---
graph = CakeDreamsGraph()
session_mgr = SessionManager()

# --- Jinja2 Filter + Startup ---
SESSION_COOKIE = "cake_session_id"


@app.on_event("startup")
async def setup():
    templates.env.filters["timestamp_format"] = (
        lambda ts: datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
        if ts else "N/A"
    )
    cleaned = session_mgr.cleanup_old_sessions()
    if cleaned:
        logger.info(f"Startup: {cleaned} alte Sessions aufgeräumt")


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


# ==========================================
# CHAT ENDPOINTS
# ==========================================

@app.get("/")
def index():
    return FileResponse("templates/index.html")


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

        # Wenn vorherige Bestellung abgeschlossen → automatisch neue Session
        session_was_reset = False
        if state.get("order_complete"):
            session_mgr.delete_session(session_id)
            state = {}
            session_was_reset = True

        state["session_id"] = session_id

        # Graph durchlaufen
        state = graph.run(state, question)

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
            "intent": state.get("intent", ""),
            "order_info": state.get("order_info", {}),
            "order_complete": state.get("order_complete", False),
            "session_reset": session_was_reset,
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


@app.get("/api/chat/stream")
async def chat_stream(request: Request, message: str):
    """Streaming chat via SSE"""
    from fastapi.responses import StreamingResponse
    import json as _json

    session_id = request.cookies.get(SESSION_COOKIE) or session_mgr.create_session_id()
    state = session_mgr.load_session(session_id) or {}

    async def event_generator():
        try:
            from openai import AsyncOpenAI
            from config import OPENAI_API_KEY, CHAT_MODEL, load_prompts_config
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            cfg = load_prompts_config()
            tone = cfg.get("bot_personality", {}).get("tone", "freundlich")

            messages = state.get("messages", [])
            messages.append({"role": "user", "content": message})

            stream = await client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": f"Du bist ein {tone} Kuchenberater für Kidstorte."},
                    *messages[-10:]
                ],
                stream=True,
                max_tokens=500,
            )
            full_response = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_response += delta
                    yield f"data: {_json.dumps({'token': delta})}\n\n"

            # Save assistant message
            messages.append({"role": "assistant", "content": full_response})
            state["messages"] = messages
            session_mgr.save_session(session_id, state)
            yield f"data: {_json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/generate-image")
async def gen_image(request_body: ChatRequest, request: Request, response: Response):
    """Generiert ein Bild basierend auf dem bisherigen Gespräch."""
    session_id = get_session_id(request, response)

    try:
        from nodes import generate_image
        state = session_mgr.load_session(session_id)
        state["user_input"] = request_body.question
        state = generate_image(state)

        # Antwort zum Verlauf hinzufügen und speichern
        state["messages"].append({"role": "assistant", "content": state["response"]})
        session_mgr.save_session(session_id, state)

        return {
            "answer": state.get("response", ""),
            "image_url": state.get("image_url"),
        }
    except Exception as e:
        logger.exception(f"Fehler bei Bildgenerierung: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})


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
    return templates.TemplateResponse("admin.html", {"request": request, "page": "login"})


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

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "page": "dashboard",
        "config": config,
        "stats": stats,
        "sessions": sessions,
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
    from config import load_prompts_config

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
# METRICS ENDPOINT
# ==========================================

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
    return JSONResponse(snapshot)


# --- Database Diagram ---
@app.get("/database-diagram")
async def database_diagram():
    """Zeige ER-Diagramm der Datenstruktur"""
    return FileResponse("er-diagramm.html", media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
