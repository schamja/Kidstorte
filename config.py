import os
import yaml
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY nicht gesetzt! Bitte .env Datei prüfen.")

# Modelle
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = "text-embedding-3-small"

# ChromaDB
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "cake_chunks"
SESSIONS_COLLECTION = "sessions"
SESSION_TTL_HOURS = 24

# Pfade
DOCS_DIR = "./documents"

# Admin
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Prompts Config
PROMPTS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "prompts_config.yaml")


def load_prompts_config() -> dict:
    """Lädt Prompts aus YAML-Datei. Wird pro Request aufgerufen für Hot-Reload."""
    with open(PROMPTS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_prompts_config(config: dict) -> None:
    """Speichert Prompts-Config zurück in YAML-Datei (Admin-Panel)."""
    with open(PROMPTS_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
