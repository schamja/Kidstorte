"""
Cake Dreams – FastAPI Server mit LangGraph Agent
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from graph import CakeDreamsGraph

# --- App ---
app = FastAPI(title="Cake Dreams Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Path("static/images").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Agent Graph ---
agent = CakeDreamsGraph()


class ChatRequest(BaseModel):
    question: str


@app.get("/")
def index():
    return FileResponse("templates/index.html")


@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        question = request.question.strip()
        if not question:
            return JSONResponse(status_code=400, content={"detail": "Keine Frage"})

        # Agent durchlaufen lassen
        state = agent.run(question)

        return {
            "answer": state.get("response", ""),
            "image_url": state.get("image_url"),
            "intent": state.get("intent", ""),
            "order_info": state.get("order_info", {}),
            "order_complete": state.get("order_complete", False),
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/generate-image")
async def gen_image(request: ChatRequest):
    """Generiert ein Bild basierend auf dem bisherigen Gespräch."""
    try:
        from nodes import generate_image
        state = agent.state.copy()
        state["user_input"] = request.question
        state = generate_image(state)

        # Antwort zum Verlauf hinzufügen
        agent.state["messages"].append({"role": "assistant", "content": state["response"]})

        return {
            "answer": state.get("response", ""),
            "image_url": state.get("image_url"),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/reset")
async def reset():
    agent.reset()
    return {"message": "Gespräch zurückgesetzt"}


@app.get("/api/state")
async def get_state():
    """Debug: Zeigt den aktuellen Agent-State."""
    return {
        "order_info": agent.state.get("order_info", {}),
        "order_complete": agent.state.get("order_complete", False),
        "intent": agent.state.get("intent", ""),
        "message_count": len(agent.state.get("messages", [])),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
