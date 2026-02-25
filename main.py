"""
Cake Dreams – FastAPI Server mit Session-basiertem LangGraph Agent
"""

import datetime
import logging
from fastapi import FastAPI, Request, Response, HTTPException, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
from graph import CakeDreamsGraph
from session_manager import SessionManager
from config import ADMIN_PASSWORD, load_prompts_config, save_prompts_config

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("cake_dreams")

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

    try:
        question = request_body.question.strip()
        if not question:
            return JSONResponse(status_code=400, content={"detail": "Keine Frage"})

        # Session-State laden
        state = session_mgr.load_session(session_id)
        state["session_id"] = session_id

        # Graph durchlaufen
        state = graph.run(state, question)

        # Session-State speichern
        session_mgr.save_session(session_id, state)

        return {
            "answer": state.get("response", ""),
            "image_url": state.get("image_url"),
            "intent": state.get("intent", ""),
            "order_info": state.get("order_info", {}),
            "order_complete": state.get("order_complete", False),
        }

    except Exception as e:
        logger.exception(f"Fehler im Chat-Endpoint: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut."}
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


# --- Database Diagram ---
@app.get("/database-diagram")
async def database_diagram():
    """Zeige ER-Diagramm der Datenstruktur"""
    return FileResponse("er-diagramm.html", media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
