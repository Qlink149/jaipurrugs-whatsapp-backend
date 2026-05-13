import json

import httpx

from qlink_chatbot.utils.env_load import (
    default_country_code,
    qlink_gupshup_api_key,
    qlink_gupshup_app_name,
    qlink_gupshup_source,
)
from qlink_chatbot.utils.logger_config import logger

PRODUCT_TEMPLATE_NAME = "jaipur_rugs_product"
JAIPURRUGS_BASE_URL = "https://www.jaipurrugs.com/"


def _normalize_destination(phone_number: str) -> str:
    digits = "".join(ch for ch in str(phone_number) if ch.isdigit())
    if len(digits) == 10:
        return f"{default_country_code}{digits}"
    return digits


def _extract_url_suffix(full_url: str) -> str:
    """Strip the base domain and return the path+query suffix for the dynamic button."""
    if full_url.startswith(JAIPURRUGS_BASE_URL):
        return full_url[len(JAIPURRUGS_BASE_URL):]
    return full_url


def send_product_template_message(phone_number: str, bot_response: dict):
    """Send a Gupshup template message with image header, body text, and View Product URL button."""
    logger.info(
        "Sending product template message",
        extra={"phone_number": phone_number, "bot_response": bot_response},
    )

    destination = _normalize_destination(phone_number=phone_number)
    url = "https://api.gupshup.io/wa/api/v1/template/msg"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "apikey": qlink_gupshup_api_key,
    }

    url_suffix = _extract_url_suffix(bot_response.get("button_url", ""))

    template_payload = {
        "id": PRODUCT_TEMPLATE_NAME,
        "params": [bot_response.get("caption", "")],
        "buttons": [{"type": "url", "parameter": url_suffix}],
    }

    message_payload = {
        "type": "image",
        "originalUrl": bot_response.get("image_url", ""),
        "previewUrl": bot_response.get("image_url", ""),
    }

    data = {
        "channel": "whatsapp",
        "source": qlink_gupshup_source,
        "destination": destination,
        "template": json.dumps(template_payload),
        "message": json.dumps(message_payload),
        "src.name": qlink_gupshup_app_name,
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "Product template message sent",
            extra={"phone_number": phone_number, "response": response.json()},
        )
        return response.json()
    except Exception as e:
        logger.error(
            "Error sending product template message",
            extra={"phone_number": phone_number, "error": str(e)},
        )
        raise e
