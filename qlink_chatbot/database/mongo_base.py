"""
MongoDB client and collection handles — single source of truth for all DB access.
"""
import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

_client = MongoClient(os.getenv("MONGO_URI"))
_db = _client["JR"]

# Session collections
sessions_collection          = _db["users"]
whatsapp_sessions_collection = _db["users_whatsapp"]

# System collections
internal_collection              = _db["internals"]
agent_alerts                     = _db["agent_alerts"]
agents_profile                   = _db["agents"]
inventory_cache_collection       = _db["inventory_cache"]
whatsapp_outbound_events_collection = _db["whatsapp_outbound_events"]
whatsapp_status_events_collection   = _db["whatsapp_status_events"]

# Public alias used by dashboard and search modules
db = _db


def _get_sessions_collection(collection_name: str = "users"):
    if collection_name == "users_whatsapp":
        return whatsapp_sessions_collection
    return sessions_collection
