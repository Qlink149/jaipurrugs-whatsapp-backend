"""
Search Middleware — unified product search entry point.

Callers import SearchFilters and call search().
Heavy DB logic lives in search_mongo.py; filter parsing in search_filters.py.
"""
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.utils.search_filters import (
    CURRENCY_FIELDS, DEFAULT_CURRENCY,
    SearchFilters,
)
from qlink_chatbot.utils.search_mongo import mongo_search

__all__ = ["SearchFilters", "search"]


async def search(filters: SearchFilters, client_ip: str = "") -> list[dict]:
    """
    Execute a product search and return formatted product dicts.
    Returns {"error": "..."} dict on no results.
    """
    try:
        currency = filters.currency if filters.currency in CURRENCY_FIELDS else DEFAULT_CURRENCY
        if currency == DEFAULT_CURRENCY and client_ip:
            currency = await _resolve_currency_from_ip(client_ip)
        currency_field = CURRENCY_FIELDS.get(currency, "INR_MRP")
        logger.info(
            f"Middleware->MongoDB: colors={filters.colors} shapes={filters.shapes} "
            f"sizes={filters.sizes} constructions={filters.constructions}"
        )
        return await mongo_search(filters, currency, currency_field)
    except Exception as e:
        logger.error(f"Middleware search error: {e}")
        return {"error": str(e)}


async def _resolve_currency_from_ip(ip: str) -> str:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            resp = await c.get(f"http://ip-api.com/json/{ip}?fields=currency,status")
            data = resp.json()
            if data.get("status") == "success":
                cur = data.get("currency", "").upper()
                if cur in CURRENCY_FIELDS:
                    return cur
    except Exception:
        pass
    return DEFAULT_CURRENCY
