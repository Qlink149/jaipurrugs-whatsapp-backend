from datetime import datetime, time, timedelta, timezone

from qlink_chatbot.database.mongo_utils import internal_collection

IST = timezone(timedelta(hours=5, minutes=30))
AGENT_STATUS_CATEGORY = "agent_status"
OFFLINE_MESSAGE = "Our agents are not live at the moment. They will connect back shortly."
BUSINESS_START = time(9, 0)
BUSINESS_END = time(20, 0)


def _schedule_open(now_ist: datetime | None = None) -> bool:
    now_ist = now_ist or datetime.now(IST)
    return now_ist.weekday() < 6 and BUSINESS_START <= now_ist.time() < BUSINESS_END


def get_agent_status() -> dict:
    now_ist = datetime.now(IST)
    doc = internal_collection.find_one({"category": AGENT_STATUS_CATEGORY}) or {}
    manual_status = doc.get("manual_status") or "accepting"
    is_schedule_open = _schedule_open(now_ist)
    is_accepting = manual_status == "accepting" and is_schedule_open

    return {
        "manual_status": manual_status,
        "is_schedule_open": is_schedule_open,
        "is_accepting_chats": is_accepting,
        "label": "Accepting Chats" if is_accepting else "Offline",
        "offline_message": OFFLINE_MESSAGE,
        "business_hours": "Monday to Saturday, 9:00 AM to 8:00 PM IST",
        "current_ist": now_ist.isoformat(),
    }


def set_agent_manual_status(manual_status: str) -> dict:
    if manual_status not in {"accepting", "offline"}:
        raise ValueError("manual_status must be accepting or offline")

    now = datetime.utcnow()
    internal_collection.update_one(
        {"category": AGENT_STATUS_CATEGORY},
        {
            "$set": {
                "category": AGENT_STATUS_CATEGORY,
                "manual_status": manual_status,
                "updated_at": now,
            }
        },
        upsert=True,
    )
    return get_agent_status()
