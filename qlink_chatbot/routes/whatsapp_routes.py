import asyncio
import re

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse, Response

from qlink_chatbot.agent.chat_agent import chat_agent
from qlink_chatbot.database.mongo_utils import (
    create_session,
    get_session_by_id,
    save_message,
    save_user_name,
)
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.whatsapp_functions.dispatch import dispatch_whatsapp_responses

whatsapp_router = APIRouter()
WHATSAPP_COLLECTION_NAME = "users_whatsapp"

_IMAGE_MD_RE = re.compile(r'!\[.*?\]\((https?://\S+?)\)')
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')


def _extract_cta(caption: str) -> tuple[str, str | None]:
    """Pull the first [View Product](...) markdown link out of caption.

    Returns (cleaned_caption, product_url) or (caption, None).
    """
    for match in _MD_LINK_RE.finditer(caption):
        label, url = match.group(1), match.group(2)
        if "view product" in label.lower() or "jaipurrugs.com/in/rugs" in url:
            cleaned = _MD_LINK_RE.sub("", caption, count=1).strip()
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
            return cleaned, url
    return caption, None


def _extract_search_cta(text: str) -> tuple[str, str | None, str | None]:
    """Pull the first search/browse markdown link out of a text block.

    Returns (cleaned_text, search_url, button_label) or (text, None, None).
    """
    for match in _MD_LINK_RE.finditer(text):
        label, url = match.group(1), match.group(2)
        if "search" in label.lower() or "browse" in label.lower() or "/search" in url:
            cleaned = _MD_LINK_RE.sub("", text, count=1).strip()
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
            # strip emoji from label for button_text
            btn_label = re.sub(r'[^\w\s]', '', label).strip() or "Search More Rugs"
            return cleaned, url, btn_label
    return text, None, None


def _build_whatsapp_responses(text: str) -> list[dict]:
    """Split bot text into WhatsApp messages.

    Blocks with an image + View Product URL become interactive_cta messages
    (real CTA button). Blocks without an image are batched into text messages.
    """
    blocks = [b.strip() for b in re.split(r'\n\n+', text.strip()) if b.strip()]
    responses: list[dict] = []
    pending_text: list[str] = []

    for block in blocks:
        match = _IMAGE_MD_RE.search(block)
        if match:
            if pending_text:
                responses.append({"type": "text", "text": "\n\n".join(pending_text)})
                pending_text = []
            image_url = match.group(1)
            caption = _IMAGE_MD_RE.sub("", block)
            caption = re.sub(r'\n\s*[-·•]\s*$', '', caption).strip()
            caption = re.sub(r'\n{3,}', '\n\n', caption).strip()
            caption, product_url = _extract_cta(caption)
            responses.append({"type": "image", "image_url": image_url, "caption": caption})
            if product_url:
                responses.append({
                    "type": "product_template",
                    "button_url": product_url,
                    "caption": "View Product",
                })
        else:
            cleaned, search_url, btn_label = _extract_search_cta(block)
            if search_url:
                if pending_text:
                    responses.append({"type": "text", "text": "\n\n".join(pending_text)})
                    pending_text = []
                if cleaned:
                    pending_text.append(cleaned)
                responses.append({
                    "type": "product_template",
                    "button_url": search_url,
                    "caption": btn_label or "Search More Rugs",
                    "button_text": btn_label,
                })
            else:
                pending_text.append(block)

    if pending_text:
        responses.append({"type": "text", "text": "\n\n".join(pending_text)})

    return responses or [{"type": "text", "text": text}]


def _extract_event(request_data: dict) -> dict:
    entry = request_data.get("entry", [])
    changes = entry[0].get("changes", []) if entry else []
    return changes[0].get("value", {}) if changes else {}


def _extract_gupshup_message(request_data: dict) -> dict:
    """Return a normalized inbound message from Gupshup callbacks."""
    event_type = request_data.get("type")
    if event_type and event_type != "message":
        return {}

    payload = request_data.get("payload") or {}
    if not payload and request_data.get("source") and request_data.get("type"):
        payload = request_data
    message_type = (payload.get("type") or request_data.get("payload", {}).get("type") or "").strip()
    content = payload.get("payload")
    if not isinstance(content, dict):
        content = payload

    text = ""
    if message_type in {"text", "txt"}:
        text = content.get("text", "")
    elif message_type in {"button_reply", "list_reply", "button"}:
        text = (
            content.get("title")
            or content.get("text")
            or content.get("postbackText", "")
        )

    phone = payload.get("source", "") or payload.get("sender", {}).get("phone", "")
    if not phone:
        return {}
    return {
        "from": phone,
        "text": (text or "").strip(),
        "name": (payload.get("sender") or {}).get("name", ""),
    }


def _extract_username(whatsapp_event: dict, fallback_name: str = "") -> str:
    contacts = whatsapp_event.get("contacts", [])
    if not contacts:
        return fallback_name
    return contacts[0].get("profile", {}).get("name", "")


def _extract_user_message_text(message_payload: dict) -> str:
    text_body = message_payload.get("text", {}).get("body", "")
    if text_body:
        return text_body.strip()

    button_text = message_payload.get("button", {}).get("text", "")
    if button_text:
        return button_text.strip()

    interactive = message_payload.get("interactive", {})
    if interactive.get("type") == "button_reply":
        return interactive.get("button_reply", {}).get("title", "").strip()

    if interactive.get("type") == "list_reply":
        return interactive.get("list_reply", {}).get("title", "").strip()

    return ""


async def _process_message(request_data: dict) -> None:
    """Process the inbound message in the background after returning 200 to Gupshup."""
    phone_number = ""
    try:
        gupshup_message = _extract_gupshup_message(request_data)

        if request_data.get("type") and request_data.get("type") != "message":
            logger.info("Ignoring non-message Gupshup callback",
                        extra={"type": request_data.get("type")})
            return

        whatsapp_event = _extract_event(request_data)

        statuses = whatsapp_event.get("statuses", [])
        if statuses:
            status = statuses[0].get("type") or statuses[0].get("status")
            logger.info(
                "Ignoring status callback",
                extra={"status": status, "statuses": statuses},
            )
            return

        incoming_messages = whatsapp_event.get("messages", [])
        if gupshup_message:
            phone_number = gupshup_message.get("from", "")
            whatsapp_username = gupshup_message.get("name", "")
            user_text = gupshup_message.get("text", "")
        elif incoming_messages:
            incoming_message = incoming_messages[0]
            phone_number = incoming_message.get("from", "")
            whatsapp_username = _extract_username(whatsapp_event)
            user_text = _extract_user_message_text(incoming_message)
        else:
            logger.info("No incoming messages in webhook payload")
            return

        if not phone_number or not user_text:
            logger.info("Skipping — missing phone or text",
                        extra={"phone_number": phone_number})
            return

        session_id = phone_number.lower()
        session = get_session_by_id(session_id=session_id,
                                    collection_name=WHATSAPP_COLLECTION_NAME)

        if not session:
            create_session(session_id=session_id, country_code="",
                           name=whatsapp_username, is_ai=True,
                           collection_name=WHATSAPP_COLLECTION_NAME)
            session = {"chat_history": [], "country_code": ""}
        elif whatsapp_username and whatsapp_username != session.get("user_name", ""):
            save_user_name(session_id=session_id, name=whatsapp_username,
                           collection_name=WHATSAPP_COLLECTION_NAME)

        save_message(session_id=session_id, role="user", content=user_text,
                     collection_name=WHATSAPP_COLLECTION_NAME)

        bot_text = await chat_agent(
            chat_history=session.get("chat_history", []),
            user_message=user_text,
            session_id=session_id,
            country_code=session.get("country_code", ""),
            client_ip="",
            collection_name=WHATSAPP_COLLECTION_NAME,
        )

        bot_text = bot_text or "Sorry, I could not generate a response right now."
        save_message(session_id=session_id, role="assistant", content=bot_text,
                     collection_name=WHATSAPP_COLLECTION_NAME)

        responses = _build_whatsapp_responses(bot_text)
        dispatch_whatsapp_responses(phone_number=phone_number, bot_responses=responses)

    except Exception as e:
        logger.exception("Exception in background message processing",
                         extra={"exception": str(e), "phone_number": phone_number})
        if phone_number:
            try:
                dispatch_whatsapp_responses(
                    phone_number=phone_number,
                    bot_responses=[{"type": "text", "text": "Unexpected error occurred."}],
                )
            except Exception as send_error:
                logger.error("Failed to send fallback message",
                             extra={"error": str(send_error), "phone_number": phone_number})


@whatsapp_router.post("/gupshup/message/hc")
async def gupshup_messages(data: Request, background_tasks: BackgroundTasks):
    """Gupshup webhook — returns empty 200 immediately, processes in background."""
    request_data = await data.json()
    logger.info("Gupshup request received", extra={"data": request_data})
    background_tasks.add_task(_process_message, request_data)
    return Response(status_code=200)
