import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY nicht gesetzt! Bitte .env Datei prüfen.")

# Modelle
CHAT_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

# ChromaDB
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "cake_chunks"

# Pfade
DOCS_DIR = "./documents"
