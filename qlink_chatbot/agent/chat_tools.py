"""
Tool schema definitions and tool call execution for chat_agent.
"""
import json

from qlink_chatbot.database.mongo_utils import (
    get_previous_search,
    raise_alert,
    save_callback_phone,
    save_previous_search,
    save_user_name,
)
from qlink_chatbot.database.pinecone_utils import fetch_similar_sessions
from qlink_chatbot.utils.logger_config import logger

from qlink_chatbot.agent.chat_context import (
    format_product_results,
    is_show_more_request,
    merge_keyword_filters,
    merge_price_filters,
    previously_shown_product_keys,
    previously_shown_product_names,
    product_search_label,
    serialize_search_filters,
)

# ── Tool schema ───────────────────────────────────────────────────────────────

tools = [
    {
        "type": "function",
        "name": "jaipur_rugs_product_search",
        "description": (
            "Search Jaipur Rugs products. Extract structured filters from the user's request "
            "and pass them as separate fields — do NOT pack everything into a single keyword string."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "colors":        {"type": "array", "items": {"type": "string"}, "description": "Color names. e.g. ['blue', 'ivory']"},
                "shapes":        {"type": "array", "items": {"type": "string"}, "description": "Rug shape. e.g. ['round'], ['runner'], ['oval']"},
                "sizes":         {"type": "array", "items": {"type": "string"}, "description": "Dimensions in WxH format. e.g. ['8x10', '5x7']"},
                "materials":     {"type": "array", "items": {"type": "string"}, "description": "Material/fabric. e.g. ['wool'], ['silk'], ['viscose']"},
                "constructions": {"type": "array", "items": {"type": "string"}, "description": "Construction type. e.g. ['hand knotted'], ['hand tufted'], ['flat weave']"},
                "styles":        {"type": "array", "items": {"type": "string"}, "description": "Design style. e.g. ['modern'], ['traditional'], ['bohemian']"},
                "price_max":     {"type": "number", "description": "Maximum price budget (in the currency field below)."},
                "price_min":     {"type": "number", "description": "Minimum price for 'above', 'over', 'at least', 'starting from'."},
                "currency":      {"type": "string", "description": "Currency for prices AND filtering. One of: INR, USD, EUR, GBP, AUD, CHF, SGD, AED."},
                "weight_max":    {"type": "number", "description": "Maximum weight in kg."},
                "keyword":       {"type": "string", "description": "Free-text fallback only when none of the above fields apply."},
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_previous_search",
        "description": "Retrieve the user's last 3–4 previous searches if they ask for it.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "User's session id"},
            },
            "required": ["session_id"],
        },
    },
    {
        "type": "function",
        "name": "search_kb",
        "description": "Semantic search in the knowledge base for past summaries or agent learnings.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text."},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "raise_agent_alert",
        "description": "Raise an alert for a human agent to take over.",
        "parameters": {
            "type": "object",
            "properties": {
                "alert": {"type": "string", "description": "Short one-line reason why agent assistance is needed."},
            },
            "required": ["alert"],
        },
    },
    {
        "type": "function",
        "name": "save_callback_phone",
        "description": "Save the user's phone number after they request a callback.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "The user's phone number including country code."},
            },
            "required": ["phone"],
        },
    },
]


# ── Tool call executor ────────────────────────────────────────────────────────

async def execute_tool_calls(
    response_output: list,
    *,
    session_id: str,
    collection_name: str,
    client_ip: str,
    detected_currency: str,
    requested_currency: str,
    show_more_request: bool,
    previous_product_filters: dict,
    exclude_product_keys: list[str],
    exclude_product_names: list[str],
    current_user_name: str,
    user_message: str,
) -> tuple[list[dict], str]:
    """
    Process all tool calls from the model's first response.

    Returns (function_call_output_items, product_response_text).
    product_response_text is non-empty only when a product search ran successfully
    (or when show-more had no more results), allowing the caller to skip Step 3.
    """
    from qlink_chatbot.utils.search_middleware import SearchFilters, search as _mw_search

    tool_outputs: list[dict] = []
    product_response_text = ""

    for item in response_output:
        if item.type != "function_call":
            continue

        args = json.loads(item.arguments)
        output = ""

        if item.name == "jaipur_rugs_product_search":
            resolved_currency = (
                args.get("currency") or requested_currency or detected_currency or "INR"
            ).upper()
            kw = args.get("keyword", "")
            message_filters = SearchFilters.from_keyword(user_message, currency=resolved_currency)

            if show_more_request and previous_product_filters:
                filters = SearchFilters.from_params(
                    colors=previous_product_filters.get("colors"),
                    shapes=previous_product_filters.get("shapes"),
                    sizes=previous_product_filters.get("sizes"),
                    materials=previous_product_filters.get("materials"),
                    constructions=previous_product_filters.get("constructions"),
                    styles=previous_product_filters.get("styles"),
                    generics=previous_product_filters.get("generics"),
                    price_max=previous_product_filters.get("price_max"),
                    price_min=previous_product_filters.get("price_min"),
                    currency=(previous_product_filters.get("currency") or resolved_currency),
                    weight_max=previous_product_filters.get("weight_max"),
                    exclude_keys=exclude_product_keys,
                    exclude_names=exclude_product_names,
                )
            elif any(args.get(f) for f in ("colors", "shapes", "sizes", "materials", "constructions", "styles", "price_max", "price_min", "weight_max")):
                filters = SearchFilters.from_params(
                    colors=args.get("colors"),
                    shapes=args.get("shapes"),
                    sizes=args.get("sizes"),
                    materials=args.get("materials"),
                    constructions=args.get("constructions"),
                    styles=args.get("styles"),
                    price_max=args.get("price_max"),
                    price_min=args.get("price_min"),
                    currency=resolved_currency,
                    weight_max=args.get("weight_max"),
                    exclude_keys=exclude_product_keys,
                    exclude_names=exclude_product_names,
                )
                merge_price_filters(filters, message_filters)
                if kw:
                    merge_keyword_filters(filters, SearchFilters.from_keyword(kw, currency=resolved_currency))
            else:
                filters = SearchFilters.from_keyword(kw or user_message, currency=resolved_currency)
                filters.exclude_keys = exclude_product_keys
                filters.exclude_names = exclude_product_names

            products = await _mw_search(filters, client_ip=client_ip)

            if isinstance(products, list) and products:
                save_previous_search(
                    session_id,
                    product_search_label(args),
                    products,
                    collection_name=collection_name,
                    filters=serialize_search_filters(filters),
                )
                product_response_text = format_product_results(
                    products, filters.currency, current_user_name, more=show_more_request
                )
                output = product_response_text or json.dumps({"error": "No priced products found."})
            else:
                if show_more_request and (previous_product_filters or exclude_product_keys):
                    product_response_text = (
                        "I couldn't find more rugs matching your criteria. "
                        "Would you like to try different filters or "
                        "[browse the full catalog](https://www.jaipurrugs.com/in/search)?"
                    )
                output = json.dumps({"error": "No products found."})

        elif item.name == "save_user_name":
            save_user_name(session_id, args.get("name"), collection_name=collection_name)
            output = json.dumps({"status": "success"})

        elif item.name == "get_previous_search":
            output = json.dumps(get_previous_search(session_id=session_id, collection_name=collection_name))

        elif item.name == "search_kb":
            kb_results = await fetch_similar_sessions(query=args.get("query"), top_k=5)
            output = json.dumps(kb_results)

        elif item.name == "raise_agent_alert":
            try:
                raise_alert(session_id=session_id, alert_body=args.get("alert"))
            except Exception:
                logger.error("Error raising agent alert")
            output = json.dumps({"status": "success"})

        elif item.name == "save_callback_phone":
            phone = args.get("phone", "")
            save_callback_phone(session_id, phone, collection_name=collection_name)
            output = json.dumps({"status": "saved", "phone": phone})

        tool_outputs.append({
            "type": "function_call_output",
            "call_id": item.call_id,
            "output": output,
        })

    return tool_outputs, product_response_text
