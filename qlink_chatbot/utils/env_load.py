import os

from dotenv import load_dotenv

load_dotenv()

gupshup_api_key = os.getenv("GUPSHUP_API_KEY", "")
gupshup_app_name = os.getenv("GUPSHUP_APP_NAME", "")
qlink_app_name = os.getenv("QLINK_APP_NAME", gupshup_app_name)
gupshup_source = os.getenv("GUPSHUP_SOURCE", "")
default_country_code = os.getenv("DEFAULT_COUNTRY_CODE", "91")

# Qliink / Kisna WhatsApp App
qlink_gupshup_app_id = os.getenv("QLINK_GUPSHUP_APP_ID", "")
qlink_gupshup_api_key = os.getenv("QLINK_GUPSHUP_API_KEY", "")
qlink_gupshup_partner_app_token = os.getenv("QLINK_GUPSHUP_PARTNER_APP_TOKEN", "")
qlink_gupshup_app_name = os.getenv("QLINK_GUPSHUP_APP_NAME", "")
qlink_gupshup_source = os.getenv("QLINK_GUPSHUP_SOURCE", "")
