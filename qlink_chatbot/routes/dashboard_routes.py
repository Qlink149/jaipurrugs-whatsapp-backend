"""
Admin dashboard router — assembles sub-routers and owns sync / prompt / agent endpoints.

Stats & conversations → dashboard_stats.py
Product CRUD          → dashboard_products.py
"""
import os
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Body, Header, HTTPException
from pymongo import UpdateOne

from qlink_chatbot.agent.utils.chat_agent_prompts import (
    system_conversation_style,
    system_identity,
    system_others,
    system_product_display_format,
)
from qlink_chatbot.database.mongo_base import internal_collection, whatsapp_sessions_collection
from qlink_chatbot.database.mongo_utils import toggle_ai
from qlink_chatbot.routes.dashboard_stats import stats_router, _jsonable
from qlink_chatbot.routes.dashboard_products import products_router
from qlink_chatbot.utils.jr_api_client import get_all_products as _jr_get_all_products
from qlink_chatbot.utils.jaipur_rugs_api import products_collection as website_products_collection
from qlink_chatbot.whatsapp_functions.dispatch import dispatch_whatsapp_responses

dashboard_router = APIRouter(prefix="/api")
dashboard_router.include_router(stats_router)
dashboard_router.include_router(products_router)

_CRON_SECRET = os.getenv("CRON_SECRET", "")


# ── Prompt management ─────────────────────────────────────────────────────────

@dashboard_router.get("/prompt")
def get_prompt():
    doc = internal_collection.find_one({"category": "system_prompt"}, {"_id": 0}) or {}
    return {"prompt": (doc.get("system_identity") or system_identity).strip()}


@dashboard_router.post("/prompt")
def save_prompt(payload: dict = Body(...)):
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    internal_collection.update_one(
        {"category": "system_prompt"},
        {"$set": {
            "category": "system_prompt",
            "system_identity": prompt,
            "system_conversation_style": system_conversation_style,
            "system_product_display_format": system_product_display_format,
            "system_others": system_others,
        }},
        upsert=True,
    )
    return {"success": True}


# ── WhatsApp manual send ──────────────────────────────────────────────────────

@dashboard_router.post("/whatsapp/send")
def send_whatsapp_message(payload: dict = Body(...)):
    phone = (payload.get("phone") or "").strip()
    message = (payload.get("message") or "").strip()
    if not phone or not message:
        raise HTTPException(status_code=400, detail="phone and message are required")
    dispatch_whatsapp_responses(phone_number=phone, bot_responses=[{"type": "text", "text": message}])
    whatsapp_sessions_collection.update_one(
        {"session_id": phone.lower()},
        {
            "$push": {"chat_history": {"role": "assistant", "content": message, "timestamp": datetime.utcnow()}},
            "$set": {"updated_at": datetime.utcnow()},
            "$setOnInsert": {"created_at": datetime.utcnow(), "country_code": "", "is_ai": True, "user_name": "Customer"},
        },
        upsert=True,
    )
    return {"success": True}


# ── Toggle AI / agent handoff ─────────────────────────────────────────────────

@dashboard_router.post("/conversations/{phone}/toggle-ai")
def toggle_conversation_ai(phone: str):
    new_status = toggle_ai(session_id=phone.strip().lower(), collection_name="users_whatsapp")
    if new_status is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"phone": phone, "is_ai": new_status}


# ── Product sync ──────────────────────────────────────────────────────────────

def _build_sync_doc(p: dict) -> dict:
    return {
        "raw": p,
        "BarCode": p.get("BarCode"),
        "SKU": p.get("SKU"),
        "flags": {"inStock": bool(p.get("LiveStatus")) and bool(p.get("Published"))},
        "search": {
            "color": {"single": p.get("GrColor", ""), "multi": p.get("ColorFamily", "")},
            "material": {
                "primary": p.get("Material", ""),
                "family": p.get("MaterialFamilies", ""),
                "details": p.get("MaterialDetails", ""),
            },
            "size": {"exact": p.get("SizeInFT", ""), "group": p.get("SizeGroupInFT", "")},
            "construction": p.get("Construction", ""),
            "style": p.get("Style", ""),
            "shape": p.get("Shape", ""),
            "price": p.get("INR_MRP"),
            "quality": p.get("Quality", ""),
            "weight": p.get("Weight", 0.0),
            "room": [r.strip() for r in (p.get("Room") or "").split(",") if r.strip()],
        },
        "updated_at": datetime.utcnow(),
    }


def _bulk_upsert(products: list[dict]) -> dict:
    now = datetime.utcnow()
    ops, skipped, barcodes = [], 0, []
    for p in products:
        barcode = p.get("BarCode")
        if not barcode:
            skipped += 1
            continue
        barcodes.append(barcode)
        ops.append(UpdateOne(
            {"BarCode": barcode},
            {"$set": _build_sync_doc(p), "$setOnInsert": {"created_at": now}},
            upsert=True,
        ))
    if not ops:
        return {"synced": 0, "skipped": skipped}
    upserted = modified = 0
    for i in range(0, len(ops), 500):
        r = website_products_collection.bulk_write(ops[i:i + 500], ordered=False)
        upserted += r.upserted_count
        modified += r.modified_count
    deleted_stale = website_products_collection.delete_many({"BarCode": {"$nin": barcodes}}).deleted_count
    return {"synced": len(ops), "upserted": upserted, "modified": modified, "skipped": skipped, "deleted_stale": deleted_stale}


@dashboard_router.post("/sync-products")
async def sync_products():
    products = await _jr_get_all_products()
    if not products:
        return {"synced": 0, "skipped": 0, "error": "JR API returned no products"}
    return _bulk_upsert(products)


@dashboard_router.get("/cron/sync-products")
async def cron_sync_products(authorization: str = Header(default="")):
    if _CRON_SECRET and authorization != f"Bearer {_CRON_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    products = await _jr_get_all_products()
    if not products:
        return {"synced": 0, "skipped": 0, "error": "JR API returned no products", "triggered_by": "cron"}
    return {**_bulk_upsert(products), "triggered_by": "cron"}


# ── Debug ─────────────────────────────────────────────────────────────────────

@dashboard_router.get("/debug/price-fields")
def debug_price_fields(limit: int = 5):
    MRP_KEYS = ["INR_MRP", "USD_MRP", "EUR_MRP", "GBP_MRP", "AUD_MRP", "CHF_MRP", "SGD_MRP", "AED_MRP"]
    docs = list(website_products_collection.find(
        {"flags.inStock": True},
        {"_id": 0, "raw.Name": 1, "raw.SKU": 1, **{f"raw.{k}": 1 for k in MRP_KEYS}},
    ).limit(limit))
    result = [{"name": d.get("raw", {}).get("Name", ""), "sku": d.get("raw", {}).get("SKU", ""), **{k: d.get("raw", {}).get(k) for k in MRP_KEYS}} for d in docs]
    null_usd = sum(1 for r in result if not r.get("USD_MRP"))
    return {"sample": result, "note": f"{null_usd}/{len(result)} sampled products have null/0 USD_MRP"}
