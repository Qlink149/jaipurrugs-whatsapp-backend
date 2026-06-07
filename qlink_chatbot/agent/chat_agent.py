"""
Main chat agent — orchestrates the two-step LLM flow (tool call → final response).

Helper functions  → chat_context.py
Tool definitions  → chat_tools.py
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

from openai import AsyncOpenAI

from qlink_chatbot.agent.chat_context import (
    cheapest_latest_amount,
    format_product_results,
    format_recent_chat_for_ai,
    format_recent_products_for_ai,
    is_currency_only_request,
    is_less_expensive_request,
    is_show_more_request,
    last_product_search_filters,
    latest_search_products,
    merge_price_filters,
    previously_shown_product_keys,
    previously_shown_product_names,
    requested_currency_from_message,
    serialize_search_filters,
)
from qlink_chatbot.agent.chat_tools import execute_tool_calls, tools
from qlink_chatbot.agent.utils.chat_agent_prompts import build_system_prompt
from qlink_chatbot.database.mongo_utils import (
    get_previous_search,
    return_system_prompt,
    save_previous_search,
    user_name,
)
from qlink_chatbot.utils.logger_config import logger

API_KEY = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=API_KEY) if API_KEY else None

_output_schema = {
    "format": {
        "type": "json_schema",
        "name": "general_agent_schema_v1",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Message to send to the user."}},
            "required": ["message"],
            "additionalProperties": False,
        },
    }
}

_IMAGE_MD_RE = re.compile(r'!\[.*?\]\((https?://\S+?)\)')


def _user_content(text: str):
    """Return plain string or multimodal list when images are embedded."""
    urls = _IMAGE_MD_RE.findall(text)
    if not urls:
        return text
    clean = _IMAGE_MD_RE.sub("", text).strip()
    content = [{"type": "input_text", "text": clean or "I have shared an image."}]
    for url in urls:
        content.append({"type": "input_image", "image_url": url, "detail": "auto"})
    return content


async def chat_agent(
    chat_history,
    user_message: str,
    session_id: str,
    country_code: str,
    client_ip: str = "",
    collection_name: str = "users",
    detected_currency: str = "",
) -> str:
    """Main Jaipur Rugs chatbot agent. Returns the assistant's reply as a string."""
    response = None
    try:
        if not client:
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        # ── Build system prompt ───────────────────────────────────────────────
        sp_vars = return_system_prompt()
        system_prompt = (
            build_system_prompt(
                system_identity=sp_vars["system_identity"],
                system_conversation_style=sp_vars["system_conversation_style"],
                system_product_display_format=sp_vars["system_product_display_format"],
                system_others=sp_vars["system_others"],
            )
            if sp_vars
            else build_system_prompt()
        )

        # ── Session context ───────────────────────────────────────────────────
        _IST = timezone(timedelta(hours=5, minutes=30))
        ist_time_str = datetime.now(_IST).strftime("%A, %I:%M %p IST")

        recent_searches = get_previous_search(session_id=session_id, collection_name=collection_name)
        latest_products_ctx = format_recent_products_for_ai(recent_searches)
        exclude_keys = previously_shown_product_keys(recent_searches)
        exclude_names = previously_shown_product_names(recent_searches)
        show_more = is_show_more_request(user_message)
        prev_filters = last_product_search_filters(recent_searches)
        req_currency = requested_currency_from_message(user_message)
        current_name = user_name(session_id=session_id, collection_name=collection_name)

        # ── Currency-only shortcut ────────────────────────────────────────────
        if req_currency and is_currency_only_request(user_message):
            latest = latest_search_products(recent_searches)
            if latest:
                return format_product_results(latest, req_currency, current_name)

        # ── Show-more early path (bypasses LLM entirely) ──────────────────────
        if show_more and prev_filters:
            from qlink_chatbot.utils.search_middleware import SearchFilters, search as _mw_search
            more_currency = (prev_filters.get("currency") or detected_currency or "INR").upper()
            filters = SearchFilters.from_params(
                colors=prev_filters.get("colors"),
                shapes=prev_filters.get("shapes"),
                sizes=prev_filters.get("sizes"),
                materials=prev_filters.get("materials"),
                constructions=prev_filters.get("constructions"),
                styles=prev_filters.get("styles"),
                generics=prev_filters.get("generics"),
                price_max=prev_filters.get("price_max"),
                price_min=prev_filters.get("price_min"),
                currency=more_currency,
                weight_max=prev_filters.get("weight_max"),
                exclude_keys=exclude_keys,
                exclude_names=exclude_names,
            )
            products = await _mw_search(filters, client_ip=client_ip)
            if isinstance(products, list) and products:
                save_previous_search(
                    session_id, "show more", products,
                    collection_name=collection_name,
                    filters=serialize_search_filters(filters),
                )
                return format_product_results(products, more_currency, current_name, more=True)
            return (
                "I couldn't find more rugs matching your criteria. "
                "Would you like to try different filters or "
                "[browse the full catalog](https://www.jaipurrugs.com/in/search)?"
            )

        # ── Less-expensive early path ─────────────────────────────────────────
        if is_less_expensive_request(user_message) and prev_filters:
            from qlink_chatbot.utils.search_middleware import SearchFilters, search as _mw_search
            less_currency = (prev_filters.get("currency") or detected_currency or "INR").upper()
            price_ceiling = cheapest_latest_amount(recent_searches, less_currency)
            filters = SearchFilters.from_params(
                colors=prev_filters.get("colors"),
                shapes=prev_filters.get("shapes"),
                sizes=prev_filters.get("sizes"),
                materials=prev_filters.get("materials"),
                constructions=prev_filters.get("constructions"),
                styles=prev_filters.get("styles"),
                generics=prev_filters.get("generics"),
                price_max=price_ceiling or prev_filters.get("price_max"),
                price_min=prev_filters.get("price_min"),
                currency=less_currency,
                weight_max=prev_filters.get("weight_max"),
                exclude_keys=exclude_keys,
                exclude_names=exclude_names,
            )
            products = await _mw_search(filters, client_ip=client_ip)
            if isinstance(products, list) and products:
                save_previous_search(
                    session_id, "less expensive", products,
                    collection_name=collection_name,
                    filters=serialize_search_filters(filters),
                )
                return format_product_results(products, less_currency, current_name, more=True)

        # ── Step 1: LLM call with tools ───────────────────────────────────────
        input_list = _build_input(
            chat_history=chat_history,
            user_message=user_message,
            ist_time_str=ist_time_str,
            country_code=country_code,
            detected_currency=detected_currency,
            latest_products_ctx=latest_products_ctx,
            prev_filters=prev_filters,
            current_name=current_name,
        )

        response = await client.responses.create(
            model="gpt-4.1-mini",
            tools=tools,
            input=input_list,
            temperature=0.2,
            instructions=system_prompt,
            max_output_tokens=2048,
            text=_output_schema,
            top_p=1,
        )
        logger.info("model response step 1", extra={"response": response})
        input_list = input_list + list(response.output)

        # ── Step 2: Execute tool calls ────────────────────────────────────────
        has_tool_calls = any(item.type == "function_call" for item in response.output)
        tool_outputs, product_text = [], ""
        if has_tool_calls:
            tool_outputs, product_text = await execute_tool_calls(
                response.output,
                session_id=session_id,
                collection_name=collection_name,
                client_ip=client_ip,
                detected_currency=detected_currency,
                requested_currency=req_currency,
                show_more_request=show_more,
                previous_product_filters=prev_filters,
                exclude_product_keys=exclude_keys,
                exclude_product_names=exclude_names,
                current_user_name=current_name,
                user_message=user_message,
            )
            input_list = input_list + tool_outputs

        # Product search completed — return pre-formatted text directly.
        if product_text:
            return product_text

        # ── Step 3: Final LLM response (non-product) ──────────────────────────
        if has_tool_calls:
            response = await client.responses.create(
                model="gpt-4.1-mini",
                instructions=system_prompt,
                input=input_list,
                text=_output_schema,
            )
            logger.info("model response step 3", extra={"response": response})

        # Extract text from the response output
        for out_item in (response.output or []):
            for content_item in (getattr(out_item, "content", None) or []):
                if getattr(content_item, "text", None):
                    return json.loads(content_item.text).get("message", "")

        logger.error("chat_agent: no text content found", extra={"session_id": session_id})
        return "I'm sorry, I couldn't generate a response. Please try again."

    except Exception as e:
        logger.error("chat_agent error", extra={"error": str(e), "session_id": session_id})
        return "I'm sorry, I ran into an issue processing your request. Could you please try again?"


def _build_input(
    *,
    chat_history,
    user_message: str,
    ist_time_str: str,
    country_code: str,
    detected_currency: str,
    latest_products_ctx: str,
    prev_filters: dict,
    current_name: str,
) -> list[dict]:
    """Assemble the developer + user message list for the LLM."""
    return [
        {"role": "developer", "content": f"Chat history:\n{format_recent_chat_for_ai(chat_history)}"},
        {"role": "developer", "content": f"Latest shown products (for follow-up questions): {latest_products_ctx}"},
        {"role": "developer", "content": f"Current date and time: {ist_time_str}"},
        {"role": "developer", "content": f"User's country code: {country_code}"},
        {"role": "developer", "content": f"User's detected local currency: {detected_currency or 'INR'}. Show product prices in this currency by default unless the user explicitly asks for a different one."},
        {"role": "developer", "content": "Any request that includes product attributes (color, size, material, construction, style, shape) OR uses words like 'show', 'find', 'search', 'give me', 'I want', 'I need' is ALWAYS a new product search — call `jaipur_rugs_product_search` immediately."},
        {"role": "developer", "content": "If the user asks to see products in a specific currency, set the `currency` field in the `jaipur_rugs_product_search` call to that currency code."},
        {"role": "developer", "content": "Price budget language: 'under', 'below', 'less than', 'up to' → price_max. 'over', 'above', 'more than', 'at least', 'starting from' → price_min."},
        {"role": "developer", "content": "If the user says 'less expensive', 'cheaper', or 'more affordable' after products were shown, search with the same filters and a lower price ceiling."},
        {"role": "developer", "content": "When `jaipur_rugs_product_search` returns products, display ALL of them. BANNED: 'I couldn't find any rugs with [currency] pricing' when products were returned."},
        {"role": "developer", "content": "PRICES MUST COME FROM TOOL DATA ONLY. Never calculate, convert, estimate, or invent any price."},
        {"role": "developer", "content": "When the user asks to show more products, call `jaipur_rugs_product_search`. The backend automatically excludes already-shown products."},
        {"role": "developer", "content": f"User name: {current_name}"},
        {"role": "developer", "content": "Never produce filler text like 'searching...' or 'one moment please'. Call the tool directly."},
        {"role": "developer", "content": "If `jaipur_rugs_product_search` returns an empty list, do NOT re-show previously shown products. Respond: 'I couldn't find more rugs matching your criteria.'"},
        {"role": "developer", "content": "PRODUCT TITLE RULE: First line of each product block MUST be the number followed by `name` in bold — exactly like `1. **Bespoke Sile**`."},
        {"role": "developer", "content": "When `jaipur_rugs_product_search` returns pre-formatted product text, output it VERBATIM. Do NOT reformat, rewrite, or add fields."},
        {"role": "developer", "content": "Show ALL products returned (up to 3). NEVER show only 1 when 2 or 3 were returned."},
        {"role": "developer", "content": "Only skip the search tool if the user asks about a SPECIFIC previously shown rug by position or name (e.g. 'price of the first one'). For ALL other requests, call `jaipur_rugs_product_search`."},
        {"role": "developer", "content": f"Previous product search filters for show-more: {json.dumps(prev_filters)}"},
        {"role": "developer", "content": "Only when the response contains actual rug results, append this at the very end: '[🔍 Search More Rugs](https://www.jaipurrugs.com/in/search)'. NOT for care, order, career, or custom rug responses."},
        {"role": "user", "content": _user_content(user_message)},
    ]
