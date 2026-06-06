import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qlink_chatbot.agent.chat_agent import format_product_results
from qlink_chatbot.routes.whatsapp_routes import _build_whatsapp_responses
from qlink_chatbot.utils import env_load
from qlink_chatbot.utils.geo_utils import country_code_for_phone, currency_for_country
from qlink_chatbot.utils.search_middleware import (
    CURRENCY_FIELDS,
    SearchFilters,
    _build_query,
    _product_url,
    search,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def test_price_parsing():
    cases = [
        ("show me rugs under 40000", "INR", {"max_amount": 40000.0}),
        ("show me rugs below 40000", "INR", {"max_amount": 40000.0}),
        ("show me rugs over 40000", "INR", {"min_amount": 40000.0}),
        ("show me rugs above 40000", "INR", {"min_amount": 40000.0}),
        ("red rugs less expensive than USD 500", "INR", {"currency": "USD", "max_amount": 500.0}),
        ("red rugs between 400 and 800", "USD", {"currency": "USD", "min_amount": 400.0, "max_amount": 800.0}),
    ]
    for text, currency, expected in cases:
        filters = SearchFilters.from_keyword(text, currency=currency)
        price_filter = filters.price_filter or {}
        for key, value in expected.items():
            assert_true(price_filter.get(key) == value, f"{text}: expected {key}={value}, got {price_filter}")
        assert_true(not filters.generics, f"{text}: generic filler should be removed, got {filters.generics}")


def test_currency_queries():
    inr = SearchFilters.from_keyword("show me rugs under 40000", currency="INR")
    inr_query = _build_query(None, [], None, [], None, [], [], [], inr.price_filter, [], [], [], [])
    inr_or = inr_query.get("$and", [{}])[0].get("$or", [])
    assert_true({"search.price": {"$gt": 0, "$lte": 40000.0}} in inr_or, "INR query must include search.price")
    assert_true({"raw.INR_MRP": {"$gt": 0, "$lte": 40000.0}} in inr_or, "INR query must include raw.INR_MRP")
    assert_true({"INR_MRP": {"$gt": 0, "$lte": 40000.0}} in inr_or, "INR query must include INR_MRP")

    usd = SearchFilters.from_keyword("show me rugs under USD 500", currency="INR")
    usd_query = _build_query(
        None, [], None, [], None, [], [], [], usd.price_filter, [], [], [], [],
        currency_field=CURRENCY_FIELDS["USD"],
    )
    usd_or = usd_query.get("$and", [{}])[0].get("$or", [])
    assert_true({"raw.USD_MRP": {"$gt": 0, "$lte": 500.0}} in usd_or, "USD query must include raw.USD_MRP")
    assert_true({"USD_MRP": {"$gt": 0, "$lte": 500.0}} in usd_or, "USD query must include USD_MRP")


def test_whatsapp_currency_detection():
    assert_true(country_code_for_phone("919999999999") == "IN", "+91 should map to IN")
    assert_true(currency_for_country("IN") == "INR", "IN should map to INR")
    assert_true(country_code_for_phone("447700900123") == "GB", "+44 should map to GB")
    assert_true(currency_for_country("GB") == "GBP", "GB should map to GBP")
    assert_true(country_code_for_phone("14155552671") == "US", "+1 should map to US")
    assert_true(currency_for_country("US") == "USD", "US should map to USD")


def test_urls_and_whatsapp_formatting():
    assert_true(
        _product_url("psh-612-cayenne-cayenne-rug", "RUG1038322")
        == "https://www.jaipurrugs.com/in/rugs/psh-612-cayenne-cayenne-rug?barcode=RUG1038322",
        "Slug URL should be normalized",
    )
    assert_true(
        _product_url("/in/rugs/psh-612-cayenne-cayenne-rug", "RUG1038322")
        == "https://www.jaipurrugs.com/in/rugs/psh-612-cayenne-cayenne-rug?barcode=RUG1038322",
        "Path URL should be normalized",
    )

    product = {
        "name": "Cayenne Rug",
        "collection": "Savana Collection",
        "size": "8x10 ft, Rectangle",
        "material": "Wool",
        "price": {"currency": "USD", "amount": 500},
        "mrp": {"USD": 500},
        "url": "https://www.jaipurrugs.com/in/rugs/psh-612-cayenne-cayenne-rug?barcode=RUG1038322",
        "image": "https://example.com/rug.jpg",
    }
    text = format_product_results([product], "USD")
    assert_true(text.startswith("1. **Cayenne Rug (Savana Collection)**"), "Product text should start with title")
    responses = _build_whatsapp_responses(text)
    assert_true(responses[0]["type"] == "interactive_cta", "Product should become WhatsApp CTA")
    assert_true(responses[0]["caption"].startswith("1. *Cayenne Rug (Savana Collection)*"), "Caption title mismatch")


def test_gupshup_env_presence():
    missing = []
    if not env_load.qlink_gupshup_app_id:
        missing.append("QLINK_GUPSHUP_APP_ID or GUPSHUP_APP_ID")
    if not env_load.qlink_gupshup_partner_app_token:
        missing.append("QLINK_GUPSHUP_PARTNER_APP_TOKEN or GUPSHUP_PARTNER_APP_TOKEN/GUPSHUP_PARTNER_TOKEN")
    if not env_load.qlink_gupshup_source:
        missing.append("QLINK_GUPSHUP_SOURCE or GUPSHUP_SOURCE")
    if missing:
        print("WARN missing Gupshup env:", ", ".join(missing))


async def test_live_mongo_optional():
    if not os.getenv("MONGO_URI"):
        print("SKIP live Mongo search: MONGO_URI is not set")
        return
    filters = SearchFilters.from_keyword("show me rugs under 40000", currency="INR")
    products = await search(filters)
    assert_true(isinstance(products, list), f"Expected products list, got {products}")
    assert_true(products, "Expected at least one product under 40000 INR")
    for product in products:
        amount = (product.get("price") or {}).get("amount") or (product.get("mrp") or {}).get("INR")
        assert_true(float(str(amount).replace(",", "")) <= 40000, f"Product exceeds budget: {product}")


async def main():
    test_price_parsing()
    test_currency_queries()
    test_whatsapp_currency_detection()
    test_urls_and_whatsapp_formatting()
    test_gupshup_env_presence()
    await test_live_mongo_optional()
    print("All product filter edge checks passed")


if __name__ == "__main__":
    asyncio.run(main())
