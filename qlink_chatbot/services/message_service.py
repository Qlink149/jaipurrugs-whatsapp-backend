"""
Unified message processing layer.

Both web (WebSocket) and WhatsApp channels call handle_user_message().
It owns: structured logging, save user msg, call AI, save assistant msg.
Channel-specific concerns (session setup, rendering, transport) stay in each route.
"""
from qlink_chatbot.agent.chat_agent import chat_agent
from qlink_chatbot.database.mongo_utils import (
    get_session_by_id,
    save_message,
)
from qlink_chatbot.utils.logger_config import logger

WEB_COLLECTION = "users"
WHATSAPP_COLLECTION = "users_whatsapp"


async def handle_user_message(
    channel: str,
    session_id: str,
    user_text: str,
    country_code: str,
    detected_currency: str,
    client_ip: str = "",
    collection_name: str = WEB_COLLECTION,
) -> str:
    """
    Unified message handler used by both web and WhatsApp adapters.

    Responsibilities:
    - Emit structured logs for both channels (key debugging goal)
    - Save the user message to MongoDB
    - Re-fetch session so chat_history includes the current user turn
    - Call chat_agent with unified parameters
    - Save the assistant response
    - Return raw assistant text (rendering is channel-specific)

    Parameters
    ----------
    channel:          "web" or "whatsapp"
    session_id:       Lowercased identifier (UUID for web, phone for WhatsApp)
    user_text:        Raw inbound message text
    country_code:     Resolved ISO-2 country code (e.g. "IN", "US")
    detected_currency: Currency code matching country (e.g. "INR", "USD")
    client_ip:        Caller IP for geo-currency fallback (empty for WhatsApp)
    collection_name:  MongoDB collection ("users" | "users_whatsapp")
    """
    session_id = session_id.lower()
    resolved_currency = (detected_currency or "INR").upper()

    logger.info(
        "channel_message_in",
        extra={
            "channel": channel,
            "session_id": session_id,
            "user_text": (user_text or "")[:120],
            "country_code": country_code,
            "detected_currency": resolved_currency,
            "collection_name": collection_name,
        },
    )

    # Persist user turn first so the re-fetched chat_history includes it.
    save_message(
        session_id=session_id,
        role="user",
        content=user_text,
        collection_name=collection_name,
    )

    # Re-fetch session so chat_history is current (includes the message we just saved).
    session = get_session_by_id(session_id=session_id, collection_name=collection_name) or {}
    chat_history = session.get("chat_history", [])

    response_text = await chat_agent(
        chat_history=chat_history,
        user_message=user_text,
        session_id=session_id,
        country_code=country_code,
        client_ip=client_ip,
        collection_name=collection_name,
        detected_currency=resolved_currency,
    )

    response_text = response_text or "Sorry, I could not generate a response right now."

    response_type = "product" if "View Product" in response_text else "text"
    logger.info(
        "channel_message_out",
        extra={
            "channel": channel,
            "session_id": session_id,
            "country_code": country_code,
            "detected_currency": resolved_currency,
            "collection_name": collection_name,
            "response_type": response_type,
            "response_length": len(response_text),
        },
    )

    save_message(
        session_id=session_id,
        role="assistant",
        content=response_text,
        collection_name=collection_name,
    )

    return response_text
