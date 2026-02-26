"""
Logging & Monitoring – Kidstorte
Strukturierte JSON-Logs + Metriken-Endpunkt
"""
import time
import logging
import json
import threading
from collections import defaultdict, deque
from datetime import datetime
from typing import Optional

# ─── Strukturierter JSON-Logger ──────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    """Gibt Logs als JSON-Zeilen aus (strukturiert, maschinenlesbar)"""
    def format(self, record: logging.LogRecord) -> str:
        log = {
            "ts":      datetime.utcnow().isoformat() + "Z",
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        for key in ("session_id", "node", "tokens", "cost_usd", "latency_ms"):
            if hasattr(record, key):
                log[key] = getattr(record, key)
        return json.dumps(log, ensure_ascii=False)


def setup_logging(level: str = "INFO", json_logs: bool = True):
    """Logging einrichten – JSON-Format oder normal"""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter() if json_logs else
                             logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
        root.addHandler(handler)


# ─── In-Memory Metriken ───────────────────────────────────────────────────────
class Metrics:
    """Thread-sichere In-Memory Metriken"""
    def __init__(self, history_size: int = 1000):
        self._lock = threading.Lock()
        self.start_time = time.time()

        # Zähler
        self.counters: dict[str, int] = defaultdict(int)

        # Latenz-History (rolling window)
        self.latencies: dict[str, deque] = defaultdict(lambda: deque(maxlen=history_size))

        # Token / Kosten
        self.total_tokens_in  = 0
        self.total_tokens_out = 0
        self.total_cost_usd   = 0.0

        # Fehler-Log (letzte 100)
        self.recent_errors: deque = deque(maxlen=100)

    def inc(self, key: str, value: int = 1):
        with self._lock:
            self.counters[key] += value

    def record_latency(self, operation: str, ms: float):
        with self._lock:
            self.latencies[operation].append(ms)

    def record_tokens(self, tokens_in: int, tokens_out: int, model: str = "gpt-4o-mini"):
        """Tokens + geschätzte Kosten erfassen"""
        # Preise pro 1k Tokens (Stand 2025)
        pricing = {
            "gpt-4o":        (0.005, 0.015),
            "gpt-4o-mini":   (0.00015, 0.0006),
            "gpt-4.1-mini":  (0.00015, 0.0006),
            "gpt-3.5-turbo": (0.0005, 0.0015),
        }
        in_price, out_price = pricing.get(model, (0.001, 0.002))
        cost = (tokens_in / 1000 * in_price) + (tokens_out / 1000 * out_price)
        with self._lock:
            self.total_tokens_in  += tokens_in
            self.total_tokens_out += tokens_out
            self.total_cost_usd   += cost

    def record_error(self, error: str, context: Optional[str] = None):
        with self._lock:
            self.recent_errors.append({
                "ts":      datetime.utcnow().isoformat() + "Z",
                "error":   error,
                "context": context,
            })
            self.counters["errors"] += 1

    def _percentile(self, data: list, p: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        return round(sorted_data[min(idx, len(sorted_data) - 1)], 2)

    def snapshot(self) -> dict:
        """Aktuellen Metriken-Snapshot zurückgeben"""
        with self._lock:
            uptime = round(time.time() - self.start_time, 1)
            latency_stats = {}
            for op, vals in self.latencies.items():
                data = list(vals)
                if data:
                    latency_stats[op] = {
                        "count":  len(data),
                        "avg_ms": round(sum(data) / len(data), 2),
                        "p50_ms": self._percentile(data, 50),
                        "p95_ms": self._percentile(data, 95),
                        "p99_ms": self._percentile(data, 99),
                        "max_ms": round(max(data), 2),
                    }
            return {
                "uptime_seconds":   uptime,
                "counters":         dict(self.counters),
                "latency":          latency_stats,
                "tokens": {
                    "input":  self.total_tokens_in,
                    "output": self.total_tokens_out,
                    "total":  self.total_tokens_in + self.total_tokens_out,
                },
                "cost_usd":         round(self.total_cost_usd, 6),
                "recent_errors":    list(self.recent_errors)[-10:],
            }


# ─── Globale Instanz ──────────────────────────────────────────────────────────
metrics = Metrics()


# ─── Decorator: Latenz messen ─────────────────────────────────────────────────
def track_latency(operation: str):
    """Decorator der Ausführungszeit einer Funktion misst"""
    def decorator(func):
        import functools
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                metrics.inc(f"{operation}.success")
                return result
            except Exception as e:
                metrics.inc(f"{operation}.error")
                metrics.record_error(str(e), operation)
                raise
            finally:
                ms = (time.time() - start) * 1000
                metrics.record_latency(operation, ms)
        return wrapper
    return decorator
