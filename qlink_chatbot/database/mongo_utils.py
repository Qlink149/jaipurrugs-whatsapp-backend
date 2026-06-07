"""
MongoDB helpers for session and message management.

System-level helpers (prompts, alerts, inventory) → mongo_system.py
DB collections and client                         → mongo_base.py
"""
from datetime import datetime

from qlink_chatbot.database.mongo_base import (
    _get_sessions_collection,
    agents_profile,
    sessions_collection,
    whatsapp_sessions_collection,
    whatsapp_status_events_collection,
    internal_collection,
)
from qlink_chatbot.database.mongo_system import (  # re-exported for callers
    delete_alert_by_id,
    get_inventory_cache,
    init_system_prompt,
    list_all_alerts,
    raise_alert,
    return_system_prompt,
    save_inventory_cache,
    update_system_prompt,
)
from qlink_chatbot.utils.logger_config import logger

# Re-export so existing callers don't need updating
__all__ = [
    "sessions_collection",
    "whatsapp_sessions_collection",
    "internal_collection",
    "whatsapp_status_events_collection",
    "agent_login",
    "save_message",
    "create_session",
    "update_session_country",
    "toggle_ai",
    "get_chat_history",
    "get_all_sessions",
    "get_session_by_id",
    "save_callback_phone",
    "save_user_name",
    "reset_is_ai_true",
    "save_previous_search",
    "get_previous_search",
    "user_name",
    # from mongo_system:
    "init_system_prompt",
    "return_system_prompt",
    "update_system_prompt",
    "raise_alert",
    "list_all_alerts",
    "delete_alert_by_id",
    "get_inventory_cache",
    "save_inventory_cache",
]


# ── Agent auth ────────────────────────────────────────────────────────────────

def agent_login(emp_id: str, password: str):
    try:
        agent = agents_profile.find_one({"emp_id": emp_id})
        if not agent:
            return {"success": False, "message": "Employee not found"}
        if agent.get("password") != password:
            return {"success": False, "message": "Invalid password"}
        return {
            "success": True,
            "data": {
                "emp_id": agent.get("emp_id"),
                "name": agent.get("name"),
                "category": agent.get("category"),
                "_id": str(agent.get("_id")),
            },
        }
    except Exception as e:
        logger.error("Agent login error", extra={"error": str(e)})
        return {"success": False, "message": "Server error"}


# ── Session management ────────────────────────────────────────────────────────

def create_session(
    session_id: str,
    country_code: str,
    name: str,
    is_ai: bool = True,
    collection_name: str = "users",
    geo: dict | None = None,
):
    try:
        now = datetime.utcnow()
        doc = {
            "session_id": session_id,
            "country_code": country_code,
            "is_ai": is_ai,
            "created_at": now,
            "updated_at": now,
            "user_name": name,
            "chat_history": [],
        }
        if geo:
            doc["geo"] = geo
        _get_sessions_collection(collection_name).insert_one(doc)
        logger.info(f"Session created: {session_id}")
    except Exception as e:
        logger.error("Error creating session", extra={"error": e})
        raise


def get_session_by_id(session_id: str, collection_name: str = "users"):
    try:
        col = _get_sessions_collection(collection_name)
        session = col.find_one({"session_id": session_id})
        if session:
            session["_id"] = str(session["_id"])
        return session
    except Exception as e:
        logger.error("Error fetching session by id", extra={"error": e})
        raise


def get_all_sessions():
    try:
        sessions = list(sessions_collection.find())
        for s in sessions:
            s["_id"] = str(s["_id"])
        return sessions
    except Exception as e:
        logger.error("Error fetching all sessions", extra={"error": e})
        raise


def update_session_country(session_id: str, country_code: str, collection_name: str = "users"):
    try:
        now = datetime.utcnow()
        result = _get_sessions_collection(collection_name).update_one(
            {"session_id": session_id},
            {"$set": {"country_code": country_code, "updated_at": now}},
        )
        logger.info(f"Updated country_code for session {session_id}")
        return result.modified_count
    except Exception as e:
        logger.error("Error updating session country", extra={"error": e})
        raise


def toggle_ai(session_id: str, collection_name: str = "users"):
    try:
        col = _get_sessions_collection(collection_name)
        session = col.find_one({"session_id": session_id})
        if not session:
            return None
        new_status = not session.get("is_ai", True)
        col.update_one(
            {"session_id": session_id},
            {"$set": {"is_ai": new_status, "updated_at": datetime.utcnow()}},
        )
        return new_status
    except Exception as e:
        logger.error("Error toggling AI status", extra={"error": e})
        raise


def reset_is_ai_true(session_id: str):
    try:
        sessions_collection.update_one(
            {"session_id": session_id},
            {"$set": {"is_ai": True}},
        )
    except Exception as e:
        logger.error("Error resetting is_ai field", extra={"error": e})
        raise


def get_chat_history(session_id: str):
    try:
        session = sessions_collection.find_one({"session_id": session_id}, {"_id": 0})
        return session.get("chat_history", []) if session else None
    except Exception as e:
        logger.error("Error fetching chat history", extra={"error": e})
        raise


# ── Message management ────────────────────────────────────────────────────────

def save_message(session_id: str, role: str, content: str, collection_name: str = "users"):
    try:
        now = datetime.utcnow()
        _get_sessions_collection(collection_name).update_one(
            {"session_id": session_id},
            {
                "$push": {"chat_history": {"role": role, "content": content, "timestamp": now}},
                "$set": {"updated_at": now},
            },
            upsert=True,
        )
    except Exception as e:
        logger.error("Error saving message", extra={"error": e})
        raise


def save_user_name(session_id: str, name: str, collection_name: str = "users"):
    try:
        now = datetime.utcnow()
        result = _get_sessions_collection(collection_name).update_one(
            {"session_id": session_id},
            {"$set": {"user_name": name, "updated_at": now}},
        )
        logger.info(f"Saved name for session {session_id}: {name}")
        return result.modified_count
    except Exception as e:
        logger.error("Error saving user name", extra={"error": e})
        raise


def save_callback_phone(session_id: str, phone: str, collection_name: str = "users"):
    try:
        now = datetime.utcnow()
        _get_sessions_collection(collection_name).update_one(
            {"session_id": session_id},
            {"$set": {"callback_phone": phone, "updated_at": now}},
            upsert=True,
        )
        logger.info(f"Saved callback phone for session {session_id}: {phone}")
    except Exception as e:
        logger.error("Error saving callback phone", extra={"error": e})
        raise


def user_name(session_id: str, collection_name: str = "users") -> str:
    try:
        session = _get_sessions_collection(collection_name).find_one(
            {"session_id": session_id}, {"_id": 0, "user_name": 1}
        )
        return session.get("user_name", "") if session else ""
    except Exception as e:
        logger.error("Error fetching user name", extra={"error": e})
        raise


# ── Search history ────────────────────────────────────────────────────────────

def save_previous_search(
    session_id: str,
    search_keyword: str,
    search_results: list,
    collection_name: str = "users",
    filters: dict | None = None,
):
    """Store the user's previous search. Keeps only the last 3 searches."""
    try:
        now = datetime.utcnow()
        _get_sessions_collection(collection_name).update_one(
            {"session_id": session_id},
            {
                "$push": {
                    "previous_searches": {
                        "$each": [{"keyword": search_keyword, "results": search_results,
                                   "filters": filters or {}, "timestamp": now}],
                        "$slice": -3,
                    }
                },
                "$set": {"updated_at": now},
            },
            upsert=True,
        )
        logger.info(f"Saved previous search for session {session_id}: {search_keyword}")
    except Exception as e:
        logger.error("Error saving previous search", extra={"error": e})
        raise


def get_previous_search(session_id: str, collection_name: str = "users"):
    try:
        session = _get_sessions_collection(collection_name).find_one(
            {"session_id": session_id},
            {"_id": 0, "previous_searches": 1, "previous_search": 1},
        )
        if session and "previous_searches" in session:
            return session["previous_searches"]
        if session and "previous_search" in session:
            return session["previous_search"]
        return []
    except Exception as e:
        logger.error("Error fetching previous search", extra={"error": e})
        raise
