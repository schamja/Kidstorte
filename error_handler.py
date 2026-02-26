"""
Strukturierte Fehlerbehandlung für Cake Dreams Agent.
Retry-Decorator, JSON-Parser mit Retry, safe_node Wrapper.
"""

import time
import json
import logging
import functools
from typing import Callable, Any

logger = logging.getLogger("cake_dreams")


# --- Custom Exceptions ---

class CakeDreamsError(Exception):
    """Basis-Exception für alle Cake Dreams Fehler."""
    pass


class LLMError(CakeDreamsError):
    """Fehler bei OpenAI API-Aufruf (transient oder permanent)."""
    pass


class LLMOutputError(CakeDreamsError):
    """LLM hat ungültige Ausgabe zurückgegeben (z.B. kein JSON)."""
    pass


class RAGError(CakeDreamsError):
    """Fehler beim Dokumentenabruf aus ChromaDB."""
    pass


class SessionError(CakeDreamsError):
    """Fehler beim Session-Laden/Speichern."""
    pass


# --- Retry Decorator ---

def retry_on_transient(max_retries: int = 3, base_delay: float = 1.0) -> Callable:
    """
    Decorator: Wiederholt Funktion bei transienten OpenAI-Fehlern
    mit exponentiellem Backoff.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            from openai import RateLimitError, APITimeoutError, APIConnectionError, InternalServerError
            transient = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)

            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except transient as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Transient-Fehler in {func.__name__} "
                            f"(Versuch {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retry in {delay}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Alle {max_retries + 1} Versuche fehlgeschlagen "
                            f"für {func.__name__}: {e}"
                        )
                        raise LLMError(
                            f"OpenAI API nicht erreichbar nach {max_retries + 1} Versuchen."
                        ) from e
            raise last_exception
        return wrapper
    return decorator


# --- LLM JSON Parser mit Retry ---

def parse_llm_json(raw_output: str, retry_func: Callable = None,
                    max_retries: int = 1, context_messages: list = None) -> dict:
    """
    Parst JSON aus LLM-Ausgabe. Bei Fehler optional erneuter LLM-Aufruf
    mit Fehlermeldung als Feedback.
    """
    cleaned = raw_output.strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as first_error:
        if retry_func and context_messages and max_retries > 0:
            logger.warning(f"JSON-Parse fehlgeschlagen: {first_error}. Retry mit Feedback...")
            error_messages = context_messages + [
                {"role": "assistant", "content": raw_output},
                {"role": "user", "content":
                    f"Deine letzte Antwort war kein gültiges JSON. Fehler: {first_error}. "
                    f"Antworte NUR mit einem gültigen JSON-Objekt, nichts anderes."}
            ]
            retry_output = retry_func(error_messages)
            return parse_llm_json(retry_output, retry_func=None, max_retries=0)

        logger.error(f"JSON-Parse fehlgeschlagen: {raw_output[:200]}")
        raise LLMOutputError(f"LLM-Ausgabe ist kein gültiges JSON") from first_error


# --- Safe Node Wrapper ---

def safe_node(fallback_response: str = "Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut."):
    """
    Decorator für Graph-Nodes. Fängt Fehler ab, loggt sie,
    und setzt eine nutzerfreundliche Fallback-Antwort.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(state: dict) -> dict:
            try:
                return func(state)
            except CakeDreamsError as e:
                logger.error(f"Bekannter Fehler in Node {func.__name__}: {e}")
                state["response"] = str(e) if str(e) else fallback_response
                return state
            except Exception as e:
                logger.exception(f"Unerwarteter Fehler in Node {func.__name__}: {e}")
                state["response"] = fallback_response
                return state
        return wrapper
    return decorator
