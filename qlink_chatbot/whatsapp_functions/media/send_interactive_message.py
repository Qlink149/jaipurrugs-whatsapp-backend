import json

import httpx

from qlink_chatbot.utils.env_load import (
    default_country_code,
    qlink_gupshup_app_id,
    qlink_gupshup_partner_app_token,
)
from qlink_chatbot.utils.logger_config import logger

_MAX_BODY_LENGTH = 1024
PARTNER_BASE_URL = "https://partner.gupshup.io"


def _normalize_destination(phone_number: str) -> str:
    digits = "".join(ch for ch in str(phone_number) if ch.isdigit())
    if len(digits) == 10:
        return f"{default_country_code}{digits}"
    return digits


def send_interactive_cta_message(phone_number: str, bot_response: dict):
    """Send an interactive CTA URL button message with an image header."""
    logger.info(
        "Sending interactive CTA message",
        extra={"phone_number": phone_number, "bot_response": bot_response},
    )

    destination = _normalize_destination(phone_number=phone_number)
    url = f"{PARTNER_BASE_URL}/partner/app/{qlink_gupshup_app_id}/v3/message"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": qlink_gupshup_partner_app_token,
        "token": qlink_gupshup_partner_app_token,
    }

    body_text = (bot_response.get("caption") or "Tap below to continue.")[:_MAX_BODY_LENGTH]
    interactive_payload = {
        "type": "cta_url",
        "body": {"text": body_text},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": bot_response.get("button_text", "View Product"),
                "url": bot_response.get("button_url", ""),
            },
        },
    }

    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": destination,
        "type": "interactive",
        "interactive": json.dumps(interactive_payload),
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        response.raise_for_status()
        logger.info(
            "Interactive CTA message sent",
            extra={"phone_number": phone_number, "response": response.json()},
        )
        return response.json()
    except Exception as e:
        logger.error(
            "Error sending interactive CTA message",
            extra={"phone_number": phone_number, "error": str(e)},
        )
        raise e
