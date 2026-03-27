"""
LangSmith Tracing – Die "Überwachungskamera" für den Kidstorte-Agenten.

Jeder Schritt (Guardrail, Classify, Extract, Generate Image etc.)
wird als Trace in LangSmith aufgezeichnet.

Setup:
    1. Account erstellen: https://smith.langchain.com
    2. API-Key generieren
    3. In .env eintragen:
        LANGSMITH_API_KEY=lsv2_...
        LANGSMITH_PROJECT=Kidstorte
        LANGSMITH_TRACING=true

Ohne LANGSMITH_API_KEY läuft alles normal — Tracing ist dann einfach aus.
"""

import os
import time
import logging
import functools
from contextlib import contextmanager

logger = logging.getLogger("kidstorte.tracing")

# ── Konfiguration aus Umgebungsvariablen ──
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "Kidstorte")
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"

# LangSmith Client (lazy init)
_client = None
_enabled = False


def _init_client():
    """Initialisiert den LangSmith-Client einmalig."""
    global _client, _enabled
    if _client is not None:
        return

    if not LANGSMITH_API_KEY or not LANGSMITH_TRACING:
        _enabled = False
        logger.info("LangSmith Tracing: AUS (kein API-Key oder deaktiviert)")
        return

    try:
        from langsmith import Client
        _client = Client(api_key=LANGSMITH_API_KEY, api_url=LANGSMITH_ENDPOINT)
        _enabled = True

        # LangSmith-Umgebungsvariablen setzen (für langchain/langsmith-Kompatibilität)
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
        os.environ["LANGCHAIN_ENDPOINT"] = LANGSMITH_ENDPOINT
        os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
        # Auch LANGSMITH_ENDPOINT setzen — RunTree liest direkt davon
        os.environ["LANGSMITH_ENDPOINT"] = LANGSMITH_ENDPOINT
        os.environ["LANGSMITH_API_KEY"] = LANGSMITH_API_KEY

        logger.info(f"LangSmith Tracing: AN (Projekt: {LANGSMITH_PROJECT})")
    except Exception as e:
        _enabled = False
        logger.warning(f"LangSmith Init fehlgeschlagen: {e}")


def is_enabled() -> bool:
    """Prüft ob LangSmith-Tracing aktiv ist."""
    if _client is None:
        _init_client()
    return _enabled


@contextmanager
def trace_run(name: str, run_type: str = "chain", inputs: dict = None, metadata: dict = None):
    """
    Context-Manager für LangSmith Traces.

    Usage:
        with trace_run("classify_intent", inputs={"user_input": "Hallo"}) as run:
            result = classify(...)
            run.end(outputs={"intent": "greeting"})
    """
    if not is_enabled():
        yield _DummyRun()
        return

    try:
        from langsmith.run_trees import RunTree
        run = RunTree(
            name=name,
            run_type=run_type,
            inputs=inputs or {},
            project_name=LANGSMITH_PROJECT,
            extra={"metadata": metadata or {}},
        )
        run.post()
        yield run
        # Nur end() aufrufen wenn noch nicht beendet
        if not getattr(run, '_ended', False):
            run.end(outputs={"status": "success"})
            run.patch()
    except Exception as e:
        logger.debug(f"LangSmith Trace-Fehler (nicht kritisch): {e}")
        yield _DummyRun()


class _DummyRun:
    """Dummy wenn LangSmith nicht aktiv ist — tut nichts."""
    def end(self, **kwargs):
        pass
    def patch(self):
        pass
    def create_child(self, **kwargs):
        return _DummyRun()
    def post(self):
        pass


def trace_node(name: str = None):
    """
    Decorator für Node-Funktionen — loggt automatisch Input/Output in LangSmith.

    Usage:
        @trace_node("classify_intent")
        def classify_and_extract(state):
            ...
    """
    def decorator(func):
        node_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(state, *args, **kwargs):
            if not is_enabled():
                return func(state, *args, **kwargs)

            # Input vorbereiten (keine Messages — zu groß)
            trace_input = {
                "user_input": state.get("user_input", ""),
                "intent": state.get("intent", ""),
                "order_info": state.get("order_info", {}),
            }

            t0 = time.time()
            try:
                with trace_run(node_name, run_type="chain", inputs=trace_input) as run:
                    result = func(state, *args, **kwargs)

                    # Output für Trace
                    trace_output = {
                        "response": (result.get("response", "") or "")[:500],
                        "intent": result.get("intent", ""),
                        "order_complete": result.get("order_complete", False),
                        "image_url": result.get("image_url", ""),
                        "duration_ms": round((time.time() - t0) * 1000),
                    }
                    run.end(outputs=trace_output)
                    run._ended = True
                    run.patch()

                return result
            except Exception as e:
                logger.debug(f"Trace-Wrapper Fehler: {e}")
                return func(state, *args, **kwargs)

        return wrapper
    return decorator


def trace_llm_call(name: str, messages: list, response: str, model: str = "", duration_ms: float = 0):
    """
    Loggt einen einzelnen LLM-Call als Trace.

    Usage:
        t0 = time.time()
        result = openai_client.chat.completions.create(...)
        trace_llm_call("guardrail_check", messages, result, model="gpt-4o-mini", duration_ms=...)
    """
    if not is_enabled():
        return

    try:
        with trace_run(name, run_type="llm", inputs={"messages": messages[-2:]}, metadata={"model": model}) as run:
            run.end(outputs={
                "response": response[:500] if response else "",
                "model": model,
                "duration_ms": round(duration_ms),
            })
            run._ended = True
            run.patch()
    except Exception as e:
        logger.debug(f"LLM Trace Fehler: {e}")


def trace_image_gen(prompt: str, provider: str, image_url: str = None, error: str = None, duration_ms: float = 0):
    """Loggt eine Bildgenerierung als Trace."""
    if not is_enabled():
        return

    try:
        with trace_run(f"image_gen_{provider}", run_type="tool",
                       inputs={"prompt": prompt[:300], "provider": provider}) as run:
            outputs = {
                "provider": provider,
                "success": image_url is not None,
                "duration_ms": round(duration_ms),
            }
            if image_url:
                outputs["image_url"] = image_url
            if error:
                outputs["error"] = error
            run.end(outputs=outputs)
            run._ended = True
            run.patch()
    except Exception as e:
        logger.debug(f"Image Trace Fehler: {e}")


def get_tracing_status() -> dict:
    """Gibt den Status des Tracing-Systems zurück (für Admin-Panel)."""
    return {
        "enabled": is_enabled(),
        "project": LANGSMITH_PROJECT if is_enabled() else None,
        "has_api_key": bool(LANGSMITH_API_KEY),
    }
