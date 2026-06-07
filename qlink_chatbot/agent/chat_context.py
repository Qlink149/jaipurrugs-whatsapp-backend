"""
Helper functions for chat_agent: product formatters, session context builders,
intent detectors, and search filter serializers.
"""
import json
import re

_CURRENCY_WORDS = {
    "rupee": "INR", "rupees": "INR", "inr": "INR",
    "dollar": "USD", "dollars": "USD", "usd": "USD",
    "pound": "GBP", "pounds": "GBP", "gbp": "GBP",
    "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "dirham": "AED", "dirhams": "AED", "aed": "AED",
    "aud": "AUD", "chf": "CHF", "sgd": "SGD",
}


# ── Chat history ──────────────────────────────────────────────────────────────

def format_recent_chat_for_ai(chat_history, limit: int = 10) -> str:
    if not chat_history:
        return ""
    recent = chat_history[-limit:]
    return "\n".join(
        f"{msg.get('role', 'user').capitalize()}: {msg.get('content', '')}"
        for msg in recent
    )


def format_recent_products_for_ai(previous_searches, max_products: int = 3) -> str:
    """Return a compact JSON view of the latest shown products for follow-up Q&A."""
    if not previous_searches:
        return "[]"
    latest = previous_searches[-1] if isinstance(previous_searches, list) else {}
    results = latest.get("results", []) if isinstance(latest, dict) else []
    if not isinstance(results, list):
        return "[]"
    compact = []
    for product in results[:max_products]:
        if not isinstance(product, dict):
            continue
        compact.append({
            "name": product.get("name", ""),
            "SKU": product.get("SKU", ""),
            "size": product.get("size", ""),
            "weight": product.get("weight", ""),
            "material": product.get("material", ""),
            "fabric": product.get("fabric", ""),
            "mrp": product.get("mrp", {}),
            "url": product.get("url", ""),
        })
    return json.dumps(compact)


# ── Previously shown product keys (for deduplication) ────────────────────────

def previously_shown_product_keys(previous_searches) -> list[str]:
    keys = []
    if not isinstance(previous_searches, list):
        return keys
    for search in previous_searches:
        if not isinstance(search, dict):
            continue
        for product in search.get("results", []) or []:
            if not isinstance(product, dict):
                continue
            for field in ("SKU", "sku", "BarCode", "barcode"):
                value = product.get(field)
                if value:
                    keys.append(str(value).strip().upper())
            url = product.get("url")
            if url and "barcode=" in url:
                keys.append(str(url).rsplit("barcode=", 1)[-1].split("&", 1)[0].strip().upper())
    return list(dict.fromkeys(keys))


def previously_shown_product_names(previous_searches) -> list[str]:
    names = []
    if not isinstance(previous_searches, list):
        return names
    for search in previous_searches:
        if not isinstance(search, dict):
            continue
        for product in search.get("results", []) or []:
            if isinstance(product, dict) and product.get("name"):
                names.append(str(product["name"]).strip())
    return list(dict.fromkeys(names))


# ── Intent detectors ──────────────────────────────────────────────────────────

def is_show_more_request(message: str) -> bool:
    text = (message or "").lower()
    return bool(re.search(
        r"\b(show|see|view|browse|search)\s+more\b|\bmore\s+(products|rugs|options)\b", text
    ))


def is_less_expensive_request(message: str) -> bool:
    text = (message or "").lower()
    return bool(re.search(
        r"\b(less expensive|less costly|cheaper|lower price|lower priced|more affordable|budget friendly)\b",
        text,
    ))


def requested_currency_from_message(message: str) -> str:
    text = (message or "").lower()
    code_match = re.search(r"\b(inr|usd|eur|gbp|aud|chf|sgd|aed)\b", text)
    if code_match:
        return code_match.group(1).upper()
    for word, code in _CURRENCY_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", text):
            return code
    return ""


def is_currency_only_request(message: str) -> bool:
    text = (message or "").lower().strip()
    if not requested_currency_from_message(text):
        return False
    return bool(re.search(
        r"\b(show|display|give|tell|price|prices|convert|change|switch)\b.*\b(in|to)\b", text,
    )) and not re.search(
        r"\b(red|blue|green|yellow|orange|purple|pink|white|black|grey|gray|brown|beige|ivory|cream|navy"
        r"|round|runner|oval|wool|silk|cotton|jute|modern|traditional|rug under|rugs under)\b",
        text,
    )


# ── Session search history helpers ────────────────────────────────────────────

def last_product_search_filters(previous_searches) -> dict:
    if not isinstance(previous_searches, list):
        return {}
    for search in reversed(previous_searches):
        if not isinstance(search, dict):
            continue
        filters = search.get("filters")
        results = search.get("results")
        if filters and isinstance(results, list) and results:
            return filters
    return {}


def latest_search_products(previous_searches) -> list[dict]:
    if not isinstance(previous_searches, list):
        return []
    for search in reversed(previous_searches):
        if not isinstance(search, dict):
            continue
        results = search.get("results")
        if isinstance(results, list) and results:
            return results
    return []


def serialize_search_filters(filters) -> dict:
    return {
        "colors": list(filters.colors or []),
        "shapes": list(filters.shapes or []),
        "sizes": list(filters.sizes or []),
        "materials": list(filters.materials or []),
        "constructions": list(filters.constructions or []),
        "styles": list(filters.styles or []),
        "generics": list(filters.generics or []),
        "price_max": (
            filters.price_filter.get("max_amount", filters.price_filter.get("amount"))
            if filters.price_filter else None
        ),
        "price_min": filters.price_filter.get("min_amount") if filters.price_filter else None,
        "currency": filters.price_filter.get("currency") if filters.price_filter else filters.currency,
        "weight_max": filters.weight_filter,
    }


def product_search_label(args: dict) -> str:
    parts = []
    for field in ("colors", "shapes", "sizes", "materials", "constructions", "styles"):
        for v in (args.get(field) or []):
            if v:
                parts.append(str(v).strip())
    if args.get("price_max"):
        parts.append(f"{args.get('currency') or 'INR'} {args.get('price_max')}")
    if args.get("price_min"):
        parts.append(f"above {args.get('currency') or 'INR'} {args.get('price_min')}")
    if args.get("weight_max"):
        parts.append(f"{args.get('weight_max')}kg")
    if args.get("keyword"):
        parts.append(str(args.get("keyword")).strip())
    return " & ".join(part for part in parts if part) or "search"


# ── Price helpers ─────────────────────────────────────────────────────────────

def _amount_is_present(value) -> bool:
    try:
        return float(str(value).replace(",", "")) > 0
    except (TypeError, ValueError):
        return bool(value)


def _format_amount(value) -> str:
    try:
        numeric = float(str(value).replace(",", ""))
        return f"{int(numeric):,}" if numeric.is_integer() else f"{numeric:,.2f}"
    except (TypeError, ValueError):
        return str(value)


def product_price_line(product: dict, currency: str) -> str:
    currency = (currency or "INR").upper()
    price = product.get("price") or {}
    amount = price.get("amount") if price.get("currency") == currency else None
    mrp = product.get("mrp") or {}
    if not _amount_is_present(amount):
        amount = mrp.get(currency)
    if _amount_is_present(amount):
        return f"Price: {currency} {_format_amount(amount)}"
    inr_amount = mrp.get("INR")
    if currency != "INR" and _amount_is_present(inr_amount):
        return f"Price: Not listed in {currency} - INR {_format_amount(inr_amount)}"
    return f"Price: Not listed in {currency}"


def product_amount_for_currency(product: dict, currency: str):
    currency = (currency or "INR").upper()
    price = product.get("price") or {}
    amount = price.get("amount") if price.get("currency") == currency else None
    if _amount_is_present(amount):
        return float(str(amount).replace(",", ""))
    mrp = product.get("mrp") or {}
    amount = mrp.get(currency)
    if _amount_is_present(amount):
        return float(str(amount).replace(",", ""))
    return None


def cheapest_latest_amount(previous_searches, currency: str):
    amounts = [
        a for a in (
            product_amount_for_currency(p, currency)
            for p in latest_search_products(previous_searches)
        )
        if a is not None
    ]
    return min(amounts) if amounts else None


# ── Product display formatter ─────────────────────────────────────────────────

def product_title_line(product: dict) -> str:
    title = str(product.get("name") or product.get("SKU") or "Jaipur Rugs Product").strip()
    collection = str(product.get("collection") or "").strip()
    if collection and collection.lower() not in title.lower():
        title = f"{title} ({collection})"
    return title


def format_product_results(
    products: list[dict], currency: str, user_display_name: str = "", more: bool = False
) -> str:
    priced = [
        p for p in (products or [])
        if isinstance(p, dict) and _amount_is_present(
            (p.get("price") or {}).get("amount") or (p.get("mrp") or {}).get(currency)
        )
    ]
    if not priced:
        return "I couldn't find matching rugs right now."

    blocks = []
    for index, product in enumerate(priced[:3], start=1):
        lines = [
            f"{index}. **{product_title_line(product)}**",
            f"- Size: {product.get('size') or 'Not listed'}",
            f"- Material: {product.get('material') or product.get('fabric') or 'Not listed'}",
            f"- {product_price_line(product, currency)}",
        ]
        if product.get("style"):
            lines.append(f"- Style: {product.get('style')}")
        if product.get("construction"):
            lines.append(f"- Construction: {product.get('construction')}")
        if product.get("url"):
            lines.append(f"- [View Product]({product.get('url')})")
        if product.get("image"):
            lines.append(f"- ![Image]({product.get('image')})")
        blocks.append("\n".join(lines))

    blocks.append("[🔍 Search More Rugs](https://www.jaipurrugs.com/in/search)")
    return "\n\n".join(blocks)


# ── Filter merging ────────────────────────────────────────────────────────────

def merge_keyword_filters(filters, keyword_filters) -> None:
    for attr in ("colors", "shapes", "sizes", "materials", "constructions", "styles", "generics"):
        merged = list(getattr(filters, attr, []) or [])
        for value in getattr(keyword_filters, attr, []) or []:
            if value not in merged:
                merged.append(value)
        setattr(filters, attr, merged)
    if not filters.price_filter and keyword_filters.price_filter:
        filters.price_filter = keyword_filters.price_filter
    if filters.weight_filter is None and keyword_filters.weight_filter is not None:
        filters.weight_filter = keyword_filters.weight_filter


def merge_price_filters(filters, keyword_filters) -> None:
    if not filters.price_filter and keyword_filters.price_filter:
        filters.price_filter = keyword_filters.price_filter
        filters.currency = keyword_filters.price_filter.get("currency", filters.currency)
    if filters.weight_filter is None and keyword_filters.weight_filter is not None:
        filters.weight_filter = keyword_filters.weight_filter
