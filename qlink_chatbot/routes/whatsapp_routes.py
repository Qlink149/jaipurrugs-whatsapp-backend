import asyncio

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import Response

from qlink_chatbot.agent.chat_agent import chat_agent
from qlink_chatbot.database.mongo_utils import (
    create_session,
    get_session_by_id,
    save_message,
    save_user_name,
    whatsapp_status_events_collection,
)
from qlink_chatbot.routes.whatsapp_formatter import (
    IMAGE_NOT_SUPPORTED_RESPONSE,
    MEDIA_SENTINEL,
    build_whatsapp_responses,
)
from qlink_chatbot.utils.geo_utils import country_code_for_phone, currency_for_country
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.whatsapp_functions.dispatch import dispatch_whatsapp_responses
from qlink_chatbot.whatsapp_functions.send_typing_indicator import (
    send_typing_indicator,
    typing_indicator_loop,
)

whatsapp_router = APIRouter()
WHATSAPP_COLLECTION_NAME = "users_whatsapp"


def _has_product_send(responses: list[dict]) -> bool:
    product_types = {"image", "interactive_cta", "product_template", "text_with_image"}
    return any(isinstance(r, dict) and r.get("type") in product_types for r in responses)


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
        text = content.get("title") or content.get("text") or content.get("postbackText", "")
    elif message_type in {"image", "video", "audio", "document", "sticker"}:
        text = MEDIA_SENTINEL

    phone = payload.get("source", "") or payload.get("sender", {}).get("phone", "")
    if not phone:
        return {}
    return {
        "from": phone,
        "text": (text or "").strip(),
        "name": (payload.get("sender") or {}).get("name", ""),
        "message_id": payload.get("id", "") or content.get("id", ""),
    }


def _extract_username(whatsapp_event: dict, fallback_name: str = "") -> str:
    contacts = whatsapp_event.get("contacts", [])
    return contacts[0].get("profile", {}).get("name", "") if contacts else fallback_name


def _extract_user_message_text(message_payload: dict) -> str:
    if message_payload.get("type") in {"image", "video", "audio", "document", "sticker"}:
        return MEDIA_SENTINEL
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
            try:
                whatsapp_status_events_collection.insert_one(
                    {"status": status, "statuses": statuses, "raw_event": whatsapp_event}
                )
            except Exception as status_save_error:
                logger.warning("Failed to persist WhatsApp status callback",
                               extra={"error": str(status_save_error)})
            logger.info("Ignoring status callback",
                        extra={"status": status, "statuses": statuses})
            return

        incoming_messages = whatsapp_event.get("messages", [])
        if gupshup_message:
            phone_number = gupshup_message.get("from", "")
            whatsapp_username = gupshup_message.get("name", "")
            user_text = gupshup_message.get("text", "")
            message_id = gupshup_message.get("message_id", "")
        elif incoming_messages:
            incoming_message = incoming_messages[0]
            phone_number = incoming_message.get("from", "")
            whatsapp_username = _extract_username(whatsapp_event)
            user_text = _extract_user_message_text(incoming_message)
            message_id = incoming_message.get("id", "")
        else:
            logger.info("No incoming messages in webhook payload")
            return

        if not phone_number or not user_text:
            logger.info("Skipping — missing phone or text",
                        extra={"phone_number": phone_number})
            return

        if user_text == MEDIA_SENTINEL:
            dispatch_whatsapp_responses(
                phone_number=phone_number,
                bot_responses=[{"type": "text", "text": IMAGE_NOT_SUPPORTED_RESPONSE}],
            )
            return

        session_id = phone_number.lower()
        session = get_session_by_id(session_id=session_id,
                                    collection_name=WHATSAPP_COLLECTION_NAME)

        phone_country_code = country_code_for_phone(phone_number)
        if not session:
            create_session(session_id=session_id, country_code=phone_country_code,
                           name=whatsapp_username, is_ai=True,
                           collection_name=WHATSAPP_COLLECTION_NAME)
            session = {"chat_history": [], "country_code": phone_country_code}
        elif whatsapp_username and whatsapp_username != session.get("user_name", ""):
            save_user_name(session_id=session_id, name=whatsapp_username,
                           collection_name=WHATSAPP_COLLECTION_NAME)

        save_message(session_id=session_id, role="user", content=user_text,
                     collection_name=WHATSAPP_COLLECTION_NAME)

        if not session.get("is_ai", True):
            logger.info("Human agent active — skipping AI response",
                        extra={"phone_number": phone_number})
            return

        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(typing_indicator_loop(message_id, stop_typing))
        detected_currency = currency_for_country(session.get("country_code", "") or phone_number)
        try:
            bot_text = await chat_agent(
                chat_history=session.get("chat_history", []),
                user_message=user_text,
                session_id=session_id,
                country_code=session.get("country_code", "") or phone_country_code,
                client_ip="",
                collection_name=WHATSAPP_COLLECTION_NAME,
                detected_currency=detected_currency,
            )
        finally:
            stop_typing.set()
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

        bot_text = bot_text or "Sorry, I could not generate a response right now."
        save_message(session_id=session_id, role="assistant", content=bot_text,
                     collection_name=WHATSAPP_COLLECTION_NAME)

        responses = build_whatsapp_responses(bot_text)
        if _has_product_send(responses):
            await send_typing_indicator(message_id)
        dispatch_whatsapp_responses(phone_number=phone_number, bot_responses=responses)

    except Exception as e:
        logger.exception("Exception in background message processing",
                         extra={"exception": str(e), "phone_number": phone_number})
        if phone_number:
            try:
                dispatch_whatsapp_responses(
                    phone_number=phone_number,
                    bot_responses=[{"type": "text", "text": "Sorry, something went wrong. Please try again."}],
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
