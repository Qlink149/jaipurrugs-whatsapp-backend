import json
import os
import re
from datetime import datetime, timedelta, timezone

from openai import AsyncOpenAI

from qlink_chatbot.agent.utils.chat_agent_prompts import build_system_prompt
from qlink_chatbot.database.mongo_utils import (
    get_previous_search,
    raise_alert,
    return_system_prompt,
    save_callback_phone,
    save_previous_search,
    save_user_name,
    user_name,
)
from qlink_chatbot.database.pinecone_utils import fetch_similar_sessions
from qlink_chatbot.utils.jaipur_rugs_api import jaipur_rugs_product_search
from qlink_chatbot.utils.logger_config import logger

API_KEY = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=API_KEY) if API_KEY else None

output_schema = {
    "format": {
        "type": "json_schema",
        "name": "general_agent_schema_v1",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to send to the user."
                }
            },
            "required": ["message"],
            "additionalProperties": False
        }
    }
}




# Tool definition
tools = [
    {
        "type": "function",
        "name": "jaipur_rugs_product_search",
        "description": "Search Jaipur Rugs products. Extract structured filters from the user's request and pass them as separate fields — do NOT pack everything into a single keyword string.",
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
                "currency":      {"type": "string", "description": "Currency code for price_max. One of: INR, USD, EUR, GBP, AUD, CHF, SGD, AED. Default INR."},
                "weight_max":    {"type": "number", "description": "Maximum weight in kg. e.g. 8 means 'under 8kg'."},
                "keyword":       {"type": "string", "description": "Free-text fallback only when none of the above fields apply. e.g. a collection name or design code."}
            },
            "required": []
        }
    },
    {
        "type": "function",
        "name": "get_previous_search",
        "description": "Retrieve the user's last 3–4 previous searches if they ask for it.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "User's username"}
            },
            "required": ["session_id"]
        }
    },
    {
        "type": "function",
        "name": "search_kb",
        "description": "Perform a semantic search in the knowledge base to find related past summaries or insights from previous conversations or agent learnings.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query text representing what the user is looking for."
                },
            },
            "required": ["query"]
        }
    },
    {
        "type": "function",
        "name": "raise_agent_alert",
        "description": "Raise an alert for a human agent to take over when the assistant cannot answer or needs support.",
        "parameters": {
            "type": "object",
            "properties": {
                "alert": {
                    "type": "string",
                    "description": "Short one-line description of why agent assistance is needed."
                }
            },
            "required": ["alert"]
        }
    },
    {
        "type": "function",
        "name": "save_callback_phone",
        "description": "Save the user's phone number after they request a callback, so agents can see it.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "The user's phone number, including country code if provided."
                }
            },
            "required": ["phone"]
        }
    },
]


_IMAGE_MD_RE = re.compile(r'!\[.*?\]\((https?://\S+?)\)')


def _user_content(text: str):
    """Return plain string for text-only messages, or a multimodal list when images are present."""
    urls = _IMAGE_MD_RE.findall(text)
    if not urls:
        return text
    clean = _IMAGE_MD_RE.sub("", text).strip()
    content = [{"type": "input_text", "text": clean or "I have shared an image."}]
    for url in urls:
        content.append({"type": "input_image", "image_url": url, "detail": "auto"})
    return content


def format_recent_chat_for_ai(chat_history, limit: int = 10) -> str:
    if not chat_history:
        return ""
    recent_msgs = chat_history[-limit:]
    formatted_lines = []
    for msg in recent_msgs:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        formatted_lines.append(f"{role}: {content}")
    return "\n".join(formatted_lines)

def format_recent_products_for_ai(previous_searches, max_products: int = 3) -> str:
    """Return a compact JSON view of the latest shown products for follow-up Q&A."""
    if not previous_searches:
        return "[]"

    latest_search = previous_searches[-1] if isinstance(previous_searches, list) else {}
    results = latest_search.get("results", []) if isinstance(latest_search, dict) else []

    compact_products = []
    for product in results[:max_products]:
        if not isinstance(product, dict):
            continue
        compact_products.append({
            "name": product.get("name", ""),
            "SKU": product.get("SKU", ""),
            "size": product.get("size", ""),
            "weight": product.get("weight", ""),
            "material": product.get("material", ""),
            "fabric": product.get("fabric", ""),
            "mrp": product.get("mrp", {}),
            "url": product.get("url", ""),
        })

    return json.dumps(compact_products)

def agent_alert_tool(alert, sesson_id):
    """Tool function to raise an agent alert"""
    try:
        raise_alert(
            session_id=sesson_id,
            alert_body=alert
        )
    except Exception:
        logger.error("Error occured while using agent alert tool call.")


async def chat_agent(
    chat_history,
    user_message,
    session_id,
    country_code,
    client_ip="",
    collection_name: str = "users",
    detected_currency: str = "",
):
    """Main Jaipur Rugs chatbot agent."""
    response = None
    try:
        if not client:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        system_prompt_variable = return_system_prompt()
        if system_prompt_variable:
            system_prompt = build_system_prompt(
                system_identity=system_prompt_variable["system_identity"],
                system_conversation_style=system_prompt_variable["system_conversation_style"],
                system_product_display_format=system_prompt_variable["system_product_display_format"],
                system_others=system_prompt_variable["system_others"],
            )
        else:
            system_prompt = build_system_prompt() 
            


        _IST = timezone(timedelta(hours=5, minutes=30))
        _now_ist = datetime.now(_IST)
        _ist_time_str = _now_ist.strftime("%A, %I:%M %p IST")

        # Fetch and format the latest shown products so the AI can answer
        # follow-up questions ("the first one", "its price in AED") accurately
        recent_searches = get_previous_search(session_id=session_id, collection_name=collection_name)
        latest_products_context = format_recent_products_for_ai(recent_searches)

        input_list = [
            {"role": "developer", "content": f"Chat history:\n{format_recent_chat_for_ai(chat_history)}"},
            {"role": "developer", "content": f"Latest shown products (use these for follow-up questions — 'the first one', 'its price', 'what material is it'): {latest_products_context}"},
            {"role": "developer", "content": f"Current date and time: {_ist_time_str}"},
            {"role": "developer", "content": f"users country code: {country_code}"},
            {"role": "developer", "content": f"User's detected local currency: {detected_currency or 'INR'}. Show product prices in this currency by default unless the user explicitly asks for a different one."},
            {
                "role": "developer",
                "content": f"user name: {user_name(session_id=session_id, collection_name=collection_name)}",
            },
            {"role": "developer", "content": "Never produce filler text like 'searching...' or 'one moment please'. If a tool is needed, directly call the tool without any extra wording."},
            {"role": "developer", "content": "When responding: do not add any narrative, status updates, waiting messages, politeness fillers, or redundant sentences. Either answer directly or call a tool directly."},
            {"role": "developer", "content": "When `jaipur_rugs_product_search` returns multiple products, include all returned products (up to 3) in the final user-visible response. Do not show only one unless only one was returned."},
            {"role": "developer", "content": "If the user asks price/size/material/weight/link for a previously shown rug, answer ONLY from the 'Latest shown products' context above — do NOT call the search tool again. For currency, use exact mrp values. If a currency value is missing or zero, say it is not listed and provide the INR price instead."},
            {"role": "developer", "content": "Only when the response contains actual rug results returned by the `jaipur_rugs_product_search` tool, append this exact line at the very end: '[🔍 Search More Rugs](https://www.jaipurrugs.com/in/search)'. Do NOT add it for cleaning, care, order, careers, custom rug, or any non-product response."},
            {"role": "user", "content": _user_content(user_message)}
        ]


        # Step 1: Model processes with tools available
        response = await client.responses.create(
            model="gpt-4.1-mini",
            tools=tools,
            input=input_list,
            temperature=0.7,
            instructions=system_prompt,
            max_output_tokens=2048,
            text=output_schema,
            top_p=1,
        )

        logger.info("model response", extra={"response": response})
        input_list += response.output


        # Step 2: Handle tool calls — collect ALL outputs before calling model again
        has_tool_calls = False
        for item in response.output:
            if item.type == "function_call":
                has_tool_calls = True
                args = json.loads(item.arguments)
                output = ""
                if item.name == "jaipur_rugs_product_search":
                    from qlink_chatbot.utils.search_middleware import SearchFilters, search as _mw_search
                    kw = args.get("keyword", "")
                    resolved_currency = (args.get("currency") or detected_currency or "INR").upper()

                    if any(args.get(f) for f in ("colors","shapes","sizes","materials","constructions","styles","price_max","weight_max")):
                        # LLM provided structured params → use middleware directly
                        filters = SearchFilters.from_params(
                            colors=args.get("colors"),
                            shapes=args.get("shapes"),
                            sizes=args.get("sizes"),
                            materials=args.get("materials"),
                            constructions=args.get("constructions"),
                            styles=args.get("styles"),
                            price_max=args.get("price_max"),
                            currency=resolved_currency,
                            weight_max=args.get("weight_max"),
                        )
                        if kw:  # merge any free-text keyword into generics
                            kw_filters = SearchFilters.from_keyword(kw, currency=resolved_currency)
                            filters.generics.extend(kw_filters.generics)
                        products = await _mw_search(filters, client_ip=client_ip)
                    else:
                        # Fallback: LLM used old keyword-only style
                        products = await jaipur_rugs_product_search(kw, client_ip=client_ip, country_code=country_code, currency=resolved_currency)
                    search_label = kw or str(args.get("colors", args.get("materials", args.get("shapes", "search"))))
                    save_previous_search(
                        session_id,
                        search_label,
                        products,
                        collection_name=collection_name,
                    )
                    output = json.dumps(products)

                elif item.name == "save_user_name":
                    name = args.get("name")
                    save_user_name(
                        session_id,
                        name,
                        collection_name=collection_name,
                    )
                    output = json.dumps({"status": "success"})

                elif item.name == "get_previous_search":
                    prev_searches = get_previous_search(
                        session_id=session_id,
                        collection_name=collection_name,
                    )
                    output = json.dumps(prev_searches)

                elif item.name == "search_kb":
                    query = args.get("query")
                    kb_search_response = await fetch_similar_sessions(query=query, top_k=5)
                    output = json.dumps(kb_search_response)

                elif item.name == "raise_agent_alert":
                    alert = args.get("alert")
                    agent_alert_tool(alert=alert, sesson_id=session_id)
                    output = json.dumps({"status": "success"})

                elif item.name == "save_callback_phone":
                    phone = args.get("phone", "")
                    save_callback_phone(session_id, phone, collection_name=collection_name)
                    output = json.dumps({"status": "saved", "phone": phone})

                input_list.append({
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": output
                })

        # Step 3: Final model response — called ONCE after all tool outputs are collected
        if has_tool_calls:
            response = await client.responses.create(
                model="gpt-4.1-mini",
                instructions=system_prompt,
                input=input_list,
                text=output_schema
            )

            logger.info("model response", extra={"response": response})

        # Find the text message output item — don't assume it's always [0]
        text_content = None
        for out_item in (response.output or []):
            try:
                for content_item in (getattr(out_item, "content", None) or []):
                    if getattr(content_item, "text", None):
                        text_content = content_item.text
                        break
            except Exception:
                pass
            if text_content:
                break

        if not text_content:
            logger.error("chat_agent: no text content found in response output",
                         extra={"response": str(response), "session_id": session_id})
            return "I'm sorry, I couldn't generate a response. Please try again."

        output = json.loads(text_content)
        return output.get("message")

    except Exception as e:
        logger.error(
            "error occurred while generating chat response",
            extra={
                "error": str(e),
                "response": response if response else "",
                "session_id": session_id
            }
        )
        raise e
