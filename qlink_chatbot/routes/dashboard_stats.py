"""
Dashboard stats, conversations, and leads endpoints.
"""
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter

from qlink_chatbot.database.mongo_base import sessions_collection, whatsapp_sessions_collection
from qlink_chatbot.utils.env_load import qlink_gupshup_source

stats_router = APIRouter()

COLORS = {
    "red", "blue", "green", "yellow", "orange", "purple", "pink", "white",
    "black", "grey", "gray", "brown", "beige", "ivory", "cream", "navy",
    "teal", "turquoise", "gold", "silver", "rust", "coral", "indigo",
    "maroon", "burgundy", "charcoal", "olive", "mustard", "peach", "lavender",
}


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(i) for i in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def _message_type(content: str) -> str:
    lower = (content or "").lower()
    for prefix, kind in [
        ("[image]", "image"), ("[list]", "list"), ("[buttons]", "buttons"),
        ("[document]", "document"), ("[document-fallback]", "document"),
        ("[template]", "template"),
    ]:
        if lower.startswith(prefix):
            return kind
    return "text"


def _session_to_conversation(session: dict) -> dict:
    history = session.get("chat_history") or []
    last = history[-1] if history else {}
    return {
        "phone": session.get("session_id", ""),
        "name": session.get("user_name") or "Customer",
        "last_message": last.get("content", ""),
        "last_message_at": _jsonable(last.get("timestamp") or session.get("updated_at")),
        "is_ai": session.get("is_ai", True),
    }


def _history_to_messages(history: list[dict]) -> list[dict]:
    return [
        {
            "direction": "inbound" if item.get("role") == "user" else "outbound",
            "role": item.get("role", ""),
            "content": item.get("content", ""),
            "message_type": _message_type(item.get("content", "")),
            "timestamp": _jsonable(item.get("timestamp")),
        }
        for item in (history or [])
    ]


@stats_router.get("/stats")
def get_stats():
    sessions = list(whatsapp_sessions_collection.find({}, {"chat_history": 1}))
    inbound = outbound = 0
    for s in sessions:
        for m in s.get("chat_history") or []:
            if m.get("role") == "user":
                inbound += 1
            else:
                outbound += 1
    return {
        "total_users": len(sessions),
        "total_leads": len(sessions),
        "total_messages": inbound + outbound,
        "inbound_messages": inbound,
        "outbound_messages": outbound,
        "whatsapp_number": qlink_gupshup_source,
    }


@stats_router.get("/dashboard/insights")
def get_dashboard_insights():
    fields = {"chat_history": 1, "previous_searches": 1, "country_code": 1, "geo": 1, "updated_at": 1}
    all_sessions = (
        list(sessions_collection.find({}, fields))
        + list(whatsapp_sessions_collection.find({}, fields))
    )
    ten_min_ago = datetime.utcnow() - timedelta(minutes=10)
    active_users = sum(
        1 for s in all_sessions
        if isinstance(s.get("updated_at"), datetime) and s["updated_at"] > ten_min_ago
    )

    keyword_counter, color_counter, location_counter, hour_counter = (
        Counter(), Counter(), Counter(), Counter()
    )
    for s in all_sessions:
        for search in (s.get("previous_searches") or []):
            kw = (search.get("keyword") or "").strip().lower()
            if kw:
                keyword_counter[kw] += 1
                for part in kw.replace("&", " ").split():
                    if part in COLORS:
                        color_counter[part] += 1
        geo = s.get("geo") or {}
        loc = geo.get("country") or geo.get("country_code") or s.get("country_code") or ""
        if loc:
            location_counter[loc.upper()] += 1
        for msg in (s.get("chat_history") or []):
            if msg.get("role") == "user":
                ts = msg.get("timestamp")
                if isinstance(ts, datetime):
                    hour_counter[(ts.hour + 5) % 24] += 1

    peak = hour_counter.most_common(1)[0][0] if hour_counter else None
    top_kw = keyword_counter.most_common(1)
    top_loc = location_counter.most_common(1)
    top_color = color_counter.most_common(1)
    web_count = sessions_collection.count_documents({})
    wa_count = whatsapp_sessions_collection.count_documents({})

    return {
        "overview": {
            "active_users": active_users,
            "total_users": web_count,
            "total_leads": wa_count,
            "total_messages": sum(len(s.get("chat_history") or []) for s in all_sessions),
        },
        "insights": {
            "most_searched_keyword": top_kw[0][0].title() if top_kw else "N/A",
            "active_time": (
                f"{peak:02d}:00 – {(peak + 1) % 24:02d}:00 IST" if peak is not None else "N/A"
            ),
            "highest_traffic_location": top_loc[0][0] if top_loc else "N/A",
            "highest_interested_color": top_color[0][0].title() if top_color else "N/A",
        },
    }


@stats_router.get("/conversations")
def get_conversations():
    sessions = whatsapp_sessions_collection.find({}).sort("updated_at", -1)
    return [_session_to_conversation(s) for s in sessions]


@stats_router.get("/conversations/{phone}")
def get_conversation(phone: str):
    session = whatsapp_sessions_collection.find_one({"session_id": phone.lower()})
    if not session:
        return {"phone": phone, "messages": []}
    return {"phone": phone, "messages": _history_to_messages(session.get("chat_history", []))}


@stats_router.get("/leads")
def get_leads():
    leads = []
    for s in whatsapp_sessions_collection.find({}).sort("updated_at", -1):
        from bson import ObjectId
        leads.append({
            "id": str(s.get("_id")),
            "phone": s.get("session_id", ""),
            "name": s.get("user_name") or "Customer",
            "status": "active" if s.get("is_ai", True) else "agent",
            "lead_type": "WhatsApp",
            "created_at": _jsonable(s.get("created_at") or s.get("updated_at")),
            "requirement": "",
            "location": s.get("country_code", ""),
        })
    return {"data": leads}
