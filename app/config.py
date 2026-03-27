import os
import yaml
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY nicht gesetzt! Bitte .env Datei prüfen.")

# Modelle
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1")   # gpt-image-1 oder dall-e-3
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")  # Multimodales Modell für Bildanalyse
EMBEDDING_MODEL = "text-embedding-3-small"

# Referenzbilder-Ordner (für multimodale Kuchensuche)
REFERENCE_IMAGE_DIR = os.getenv("REFERENCE_IMAGE_DIR", "Bilder")

# ChromaDB
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "cake_chunks"
SESSIONS_COLLECTION = "sessions"
SESSION_TTL_HOURS = 24

# Pfade
DOCS_DIR = "./documents"

# Admin
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# SMTP E-Mail
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
DESIGNER_EMAIL = os.getenv("DESIGNER_EMAIL", "")
SHOP_NAME = os.getenv("SHOP_NAME", "Kidstorte")

# Cal.com Kalender-Integration
CAL_API_KEY = os.getenv("CAL_API_KEY", "")
CAL_EVENT_TYPE_ID = os.getenv("CAL_EVENT_TYPE_ID", "")
CAL_USERNAME = os.getenv("CAL_USERNAME", "")

# Prompts Config
# Pfad relativ zum Projekt-Root (eine Ebene hoch aus app/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
PROMPTS_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "prompts", "prompts_config.yaml")


_prompts_cache = {"data": None, "mtime": 0}

#der schlaue leser
def load_prompts_config() -> dict:
    """Lädt Prompts aus YAML-Datei. Gecached mit mtime-Check für Hot-Reload."""
    mtime = os.path.getmtime(PROMPTS_CONFIG_PATH)
    if _prompts_cache["data"] is not None and mtime == _prompts_cache["mtime"]:
        return _prompts_cache["data"]
    with open(PROMPTS_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _prompts_cache["data"] = data
    _prompts_cache["mtime"] = mtime
    return data

#Der Schreiber für das Admin-Panel
def save_prompts_config(config: dict) -> None:
    """Speichert Prompts-Config zurück in YAML-Datei (Admin-Panel)."""
    with open(PROMPTS_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


#"Ich habe ein Hot-Reload-System für meine Prompts implementiert. Durch den mtime-Check in
# der config.py erkennt der Agent Änderungen an seinen Anweisungen sofort, ohne dass ich den
# Server neu starten muss. Das ermöglicht ein schnelles Iterieren und gibt mir die Möglichkeit,
# ein Admin-Interface für die Texteinstellungen anzubieten."