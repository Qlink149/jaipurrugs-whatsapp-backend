import json

import httpx

from qlink_chatbot.utils.env_load import (
    default_country_code,
    qlink_gupshup_app_id,
    qlink_gupshup_partner_app_token,
)
from qlink_chatbot.utils.logger_config import logger

PARTNER_BASE_URL = "https://partner.gupshup.io"


def _normalize_destination(phone_number: str) -> str:
    digits = "".join(ch for ch in str(phone_number) if ch.isdigit())
    if len(digits) == 10:
        return f"{default_country_code}{digits}"
    return digits


def send_text_message(phone_number: str, bot_response: str):
    """Sends a text message to a phone number."""
    logger.info(
        "Sending text message to phone number with message",
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

    text = bot_response.get("text", "") if isinstance(bot_response, dict) else str(bot_response)
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": destination,
        "type": "text",
        "text": json.dumps({"body": text}),
    }

    logger.info(
        "Resolved gupshup routing",
        extra={
            "destination": destination,
            "app_id": qlink_gupshup_app_id,
        },
    )

    try:
        response = httpx.post(url, headers=headers, data=data)
        response.raise_for_status()
        logger.info(
            "Response",
            extra={
                "phone_number": phone_number,
                "response": response.json(),
            },
        )
        return response.json()
    except Exception as e:
        logger.error(
            "Error in sending text message",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
