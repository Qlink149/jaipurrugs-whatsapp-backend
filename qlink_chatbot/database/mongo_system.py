"""
MongoDB helpers for system-level data: system prompt, agent alerts, inventory cache.
"""
import time
from datetime import datetime

from bson import ObjectId

from qlink_chatbot.database.mongo_base import (
    agent_alerts,
    internal_collection,
    inventory_cache_collection,
)
from qlink_chatbot.utils.logger_config import logger


# ── System prompt ─────────────────────────────────────────────────────────────

def init_system_prompt():
    """Seed the system_prompt doc from the static file if it doesn't exist yet."""
    try:
        if internal_collection.find_one({"category": "system_prompt"}, {"_id": 1}):
            logger.info("System prompt already in MongoDB.")
            return
        from qlink_chatbot.agent.utils.chat_agent_prompts import (
            system_identity,
            system_conversation_style,
            system_product_display_format,
            system_others,
        )
        internal_collection.insert_one({
            "category": "system_prompt",
            "system_identity": system_identity.strip(),
            "system_conversation_style": system_conversation_style.strip(),
            "system_product_display_format": system_product_display_format.strip(),
            "system_others": system_others.strip(),
        })
        logger.info("System prompt seeded into MongoDB.")
    except Exception as e:
        logger.error("Error seeding system prompt", extra={"error": e})


def return_system_prompt():
    try:
        return internal_collection.find_one({"category": "system_prompt"}, {"_id": 0})
    except Exception as e:
        logger.error("Error fetching system prompt", extra={"error": e})
        raise


def update_system_prompt(
    system_identity: str,
    system_conversation_style: str,
    system_product_display_format: str,
    system_others: str,
):
    try:
        update_fields = {
            "system_identity": system_identity,
            "system_conversation_style": system_conversation_style,
            "system_product_display_format": system_product_display_format,
            "system_others": system_others,
        }
        result = internal_collection.update_one(
            {"category": "system_prompt"},
            {"$set": update_fields},
            upsert=False,
        )
        if result.modified_count > 0:
            return {"status": "success", "updated_fields": list(update_fields.keys())}
        return {"status": "no_change"}
    except Exception as e:
        logger.error("Error updating system prompt", extra={"error": e})
        raise


# ── Agent alerts ──────────────────────────────────────────────────────────────

def raise_alert(session_id: str, alert_body: str):
    try:
        agent_alerts.insert_one({
            "session_id": session_id,
            "alert": alert_body,
            "created_at": int(time.time()),
        })
    except Exception as e:
        logger.error("Error raising agent alert.", extra={"error": e})
        raise


def list_all_alerts():
    try:
        result = list(agent_alerts.find())
        if not result:
            return None
        for i in result:
            i["_id"] = str(i["_id"])
        return result
    except Exception as e:
        logger.error("Error fetching agent alerts", extra={"error": e})
        raise


def delete_alert_by_id(id: str):
    try:
        result = agent_alerts.delete_one({"_id": ObjectId(id)})
        return result.deleted_count > 0
    except Exception as e:
        logger.error("Error deleting alert by ID", extra={"error": e})
        raise


# ── Inventory cache ───────────────────────────────────────────────────────────

def get_inventory_cache():
    try:
        return inventory_cache_collection.find_one({"_id": "inventory_master"})
    except Exception as e:
        logger.error("Error fetching inventory cache", extra={"error": e})
        return None


def save_inventory_cache(data: list):
    try:
        now = datetime.utcnow()
        inventory_cache_collection.update_one(
            {"_id": "inventory_master"},
            {"$set": {"data": data, "last_fetched": now}},
            upsert=True,
        )
        logger.info(f"Saved inventory cache with {len(data)} records at {now}")
    except Exception as e:
        logger.error("Error saving inventory cache", extra={"error": e})
        raise
