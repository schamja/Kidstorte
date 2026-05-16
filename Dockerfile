# syntax=docker/dockerfile:1.6
# ─────────────────────────────────────────────────────────────
# Kidstorte — Cake-Chatbot (FastAPI + ChromaDB + OpenAI)
# Multi-stage Build: schlankes Final-Image (~250 MB)
# ─────────────────────────────────────────────────────────────

# ── Stage 1: Builder (kompiliert Wheels) ──
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-Deps für chromadb (onnxruntime), reportlab, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

# Wheels in /wheels vorab bauen — landet später ohne Compiler im Final-Image
RUN pip wheel --wheel-dir=/wheels -r requirements.txt


# ── Stage 2: Runtime (das was wirklich läuft) ──
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Berlin

# Minimale Runtime-Deps (curl für Healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# Non-root User — niemals als root in Production!
RUN useradd --create-home --shell /bin/bash --uid 1000 kidstorte

WORKDIR /app

# Wheels aus Builder-Stage installieren
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

# App-Code kopieren (nach .dockerignore — schlank)
COPY --chown=kidstorte:kidstorte . .

# Persistente Verzeichnisse anlegen (werden später als Volumes gemountet)
RUN mkdir -p \
        /app/chroma_db \
        /app/static/images \
        /app/static/pdfs \
        /app/Bilder \
        /app/services \
    && chown -R kidstorte:kidstorte /app

USER kidstorte

EXPOSE 5001

# Healthcheck — Docker erkennt selbst, wenn der Container hängt
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5001/api/calendar/status || exit 1

# Ein Worker — der In-Memory-Cache (_IMAGE_CACHE) und SessionManager
# sind nicht prozess-übergreifend. Skalieren = mehr Container, nicht mehr Worker.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001", "--workers", "1"]
