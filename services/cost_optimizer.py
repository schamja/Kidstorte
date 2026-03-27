"""
Cost Optimization – Kidstorte
Token-Tracking, Response-Caching, intelligente Model-Auswahl
"""
import hashlib
import time
import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("cake_dreams.cost")

# ─── Preise (Stand 2025, per 1k Tokens) ──────────────────────────────────────
MODEL_PRICING = {
    "gpt-4o":        {"input": 0.005,   "output": 0.015},
    "gpt-4o-mini":   {"input": 0.00015, "output": 0.0006},
    "gpt-4o-mini":  {"input": 0.00015, "output": 0.0006},
    "gpt-3.5-turbo": {"input": 0.0005,  "output": 0.0015},
}

# ─── Model-Routing: Welches Modell für welche Aufgabe? ────────────────────────
TASK_MODEL_MAP = {
    "classify":    "gpt-4o-mini",   # Intent-Klassifikation → günstig
    "extract":     "gpt-4o-mini",   # Felder extrahieren → günstig
    "generate":    "gpt-4o-mini",   # Antwort generieren → Standard
    "rag_query":   "gpt-4o-mini",   # RAG-Abfrage → günstig
    "complex":     "gpt-4o",         # Komplexe Konversation → besser
}

def get_model_for_task(task: str) -> str:
    """Wählt das günstigste geeignete Modell für eine Aufgabe"""
    return TASK_MODEL_MAP.get(task, "gpt-4o-mini")

def estimate_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    """Schätzt Kosten in USD"""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["gpt-4o-mini"])
    return (tokens_in / 1000 * pricing["input"]) + (tokens_out / 1000 * pricing["output"])

# ─── Response Cache ───────────────────────────────────────────────────────────
class ResponseCache:
    """
    Einfacher In-Memory Cache für LLM-Antworten.
    Spart Kosten bei wiederholten ähnlichen Anfragen.
    """
    def __init__(self, max_size: int = 200, ttl_seconds: int = 3600):
        self._cache: dict = {}
        self._timestamps: dict = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self.hits = 0
        self.misses = 0

    def _key(self, prompt: str, model: str) -> str:
        return hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()[:16]

    def get(self, prompt: str, model: str) -> Optional[str]:
        key = self._key(prompt, model)
        if key in self._cache:
            if time.time() - self._timestamps[key] < self._ttl:
                self.hits += 1
                logger.debug(f"Cache HIT (key={key[:8]})")
                return self._cache[key]
            else:
                del self._cache[key]
                del self._timestamps[key]
        self.misses += 1
        return None

    def set(self, prompt: str, model: str, response: str):
        if len(self._cache) >= self._max_size:
            # Ältesten Eintrag entfernen (LRU-ähnlich)
            oldest = min(self._timestamps, key=self._timestamps.get)
            del self._cache[oldest]
            del self._timestamps[oldest]
        key = self._key(prompt, model)
        self._cache[key] = response
        self._timestamps[key] = time.time()

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 3) if total > 0 else 0.0

    def stats(self) -> dict:
        return {
            "size":     len(self._cache),
            "hits":     self.hits,
            "misses":   self.misses,
            "hit_rate": self.hit_rate,
        }


# ─── Token-Schätzer ───────────────────────────────────────────────────────────
def estimate_tokens(text: str) -> int:
    """Grobe Token-Schätzung ohne tiktoken (4 Zeichen ≈ 1 Token)"""
    return max(1, len(text) // 4)

def truncate_messages(messages: list, max_tokens: int = 3000) -> list:
    """
    Kürzt den Nachrichten-Verlauf auf max_tokens.
    Behält immer die erste und letzte Nachricht.
    """
    if not messages:
        return messages

    total = sum(estimate_tokens(m.get("content", "")) for m in messages)
    if total <= max_tokens:
        return messages

    # System-Nachrichten und letzte Nachricht immer behalten
    result = []
    kept_tokens = 0
    budget = max_tokens

    # Letzte Nachricht reservieren
    last = messages[-1]
    last_tokens = estimate_tokens(last.get("content", ""))
    budget -= last_tokens

    # Älteste zuerst weglassen
    for msg in messages[:-1]:
        t = estimate_tokens(msg.get("content", ""))
        if kept_tokens + t <= budget:
            result.append(msg)
            kept_tokens += t

    result.append(last)
    skipped = len(messages) - len(result)
    if skipped > 0:
        logger.info(f"Nachrichten gekürzt: {skipped} ältere Nachrichten weggelassen")
    return result


# ─── Globale Instanz ──────────────────────────────────────────────────────────
response_cache = ResponseCache()
