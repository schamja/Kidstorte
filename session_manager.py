"""
Session Manager – ChromaDB-basierte Session-Persistenz.
Spiegelt das LangGraph Checkpointer-Pattern wider:
  thread_id = session_id
  Checkpoint = serialisierter AgentState als ChromaDB-Dokument
"""

import json
import time
import uuid
import logging
import chromadb
from config import CHROMA_DB_PATH, SESSIONS_COLLECTION, SESSION_TTL_HOURS

logger = logging.getLogger("cake_dreams")


class SessionManager:
    """
    Verwaltet User-Sessions über eine ChromaDB-Collection.
    Jede Session wird als Dokument in der "sessions"-Collection gespeichert.
    """

    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name=SESSIONS_COLLECTION,
            metadata={"description": "User chat sessions"}
        )

    def create_session_id(self) -> str:
        """Erzeugt eine neue eindeutige Session-ID."""
        return uuid.uuid4().hex

    def get_default_state(self) -> dict:
        """Gibt einen frischen AgentState zurück."""
        return {
            "user_input": "",
            "messages": [],
            "intent": "",
            "order_info": {},
            "missing_fields": [],
            "order_complete": False,
            "context": "",
            "sources": [],
            "response": "",
            "image_url": None,
        }

    def load_session(self, session_id: str) -> dict:
        """
        Lädt Session-State aus ChromaDB.
        Gibt gespeicherten State zurück, oder frischen Default-State falls nicht gefunden.
        """
        try:
            result = self.collection.get(
                ids=[session_id], include=["documents", "metadatas"]
            )
            if result and result["ids"] and result["documents"][0]:
                state = json.loads(result["documents"][0])
                logger.info(
                    f"Session geladen: {session_id[:12]}... "
                    f"({len(state.get('messages', []))} Nachrichten)"
                )

                # last_accessed aktualisieren
                self.collection.update(
                    ids=[session_id],
                    metadatas=[{
                        "last_accessed": time.time(),
                        "created": result["metadatas"][0].get("created", time.time()),
                        "message_count": len(state.get("messages", []))
                    }]
                )
                return state
        except Exception as e:
            logger.error(f"Fehler beim Laden der Session {session_id[:12]}...: {e}")

        return self.get_default_state()

    def save_session(self, session_id: str, state: dict) -> None:
        """
        Speichert Session-State in ChromaDB.
        Nutzt upsert — funktioniert für neue und bestehende Sessions.
        """
        try:
            serializable_state = {
                "user_input": state.get("user_input", ""),
                "messages": state.get("messages", []),
                "intent": state.get("intent", ""),
                "order_info": state.get("order_info", {}),
                "missing_fields": state.get("missing_fields", []),
                "order_complete": state.get("order_complete", False),
                "context": "",      # RAG-Kontext nicht persistieren
                "sources": [],      # Quellen nicht persistieren
                "response": state.get("response", ""),
                "image_url": state.get("image_url"),
            }

            state_json = json.dumps(serializable_state, ensure_ascii=False)

            # Prüfen ob Session schon existiert (für created-Timestamp)
            created = time.time()
            try:
                existing = self.collection.get(ids=[session_id])
                if existing and existing["ids"] and existing["metadatas"]:
                    created = existing["metadatas"][0].get("created", created)
            except Exception:
                pass

            self.collection.upsert(
                ids=[session_id],
                documents=[state_json],
                metadatas=[{
                    "created": created,
                    "last_accessed": time.time(),
                    "message_count": len(serializable_state["messages"]),
                    "has_order": bool(serializable_state.get("order_info")),
                    "order_complete": serializable_state.get("order_complete", False),
                }]
            )
            logger.info(f"Session gespeichert: {session_id[:12]}...")

        except Exception as e:
            logger.error(f"Fehler beim Speichern der Session {session_id[:12]}...: {e}")

    def delete_session(self, session_id: str) -> None:
        """Löscht eine bestimmte Session."""
        try:
            self.collection.delete(ids=[session_id])
            logger.info(f"Session gelöscht: {session_id[:12]}...")
        except Exception as e:
            logger.error(f"Fehler beim Löschen der Session {session_id[:12]}...: {e}")

    def list_sessions(self) -> list:
        """
        Listet alle aktiven Sessions mit Metadaten.
        Sortiert nach letztem Zugriff (neueste zuerst).
        """
        try:
            result = self.collection.get(include=["metadatas"])
            sessions = []
            for sid, meta in zip(result["ids"], result["metadatas"]):
                sessions.append({
                    "session_id": sid,
                    "created": meta.get("created", 0),
                    "last_accessed": meta.get("last_accessed", 0),
                    "message_count": meta.get("message_count", 0),
                    "has_order": meta.get("has_order", False),
                    "order_complete": meta.get("order_complete", False),
                })
            sessions.sort(key=lambda s: s["last_accessed"], reverse=True)
            return sessions
        except Exception as e:
            logger.error(f"Fehler beim Auflisten der Sessions: {e}")
            return []

    def cleanup_old_sessions(self) -> int:
        """
        Entfernt Sessions die älter als SESSION_TTL_HOURS sind.
        Gibt die Anzahl gelöschter Sessions zurück.
        """
        try:
            cutoff = time.time() - (SESSION_TTL_HOURS * 3600)
            result = self.collection.get(include=["metadatas"])
            to_delete = []
            for sid, meta in zip(result["ids"], result["metadatas"]):
                if meta.get("last_accessed", 0) < cutoff:
                    to_delete.append(sid)

            if to_delete:
                self.collection.delete(ids=to_delete)
                logger.info(f"{len(to_delete)} abgelaufene Sessions aufgeräumt")

            return len(to_delete)
        except Exception as e:
            logger.error(f"Fehler beim Aufräumen der Sessions: {e}")
            return 0

    def get_statistics(self) -> dict:
        """Gibt Statistiken für das Admin-Panel zurück."""
        sessions = self.list_sessions()
        return {
            "total_sessions": len(sessions),
            "active_sessions_1h": sum(
                1 for s in sessions if s["last_accessed"] > time.time() - 3600
            ),
            "total_orders": sum(1 for s in sessions if s["has_order"]),
            "completed_orders": sum(1 for s in sessions if s["order_complete"]),
            "total_messages": sum(s["message_count"] for s in sessions),
        }
