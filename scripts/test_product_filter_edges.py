import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qlink_chatbot.agent.chat_agent import format_product_results
# _build_whatsapp_responses is still importable from the route module (backward compat shim)
from qlink_chatbot.routes.whatsapp_routes import _build_whatsapp_responses
from qlink_chatbot.utils.geo_utils import country_code_for_phone, currency_for_country
from qlink_chatbot.utils.search_middleware import (
    CURRENCY_FIELDS,
    SearchFilters,
    _build_query,
    _normalize_size_input,
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


def test_size_normalization():
    cases = [
        ("8x10", "8x10"),
        ("8 x 10", "8x10"),
        ("8X10", "8x10"),
        ("8*10", "8x10"),
        ("8 by 10", "8x10"),
        ("8x10 ft", "8x10"),
        ("5x7", "5x7"),
        ("not a size", ""),
        ("modern geometric", ""),
    ]
    for text, expected in cases:
        result = _normalize_size_input(text)
        assert_true(result == expected, f"_normalize_size_input({text!r}) = {result!r}, want {expected!r}")

    for text in ("8x10", "8 x 10", "8X10", "8*10", "8 by 10", "8x10 ft"):
        f = SearchFilters.from_keyword(f"hand knotted wool rug {text}", currency="INR")
        assert_true("8x10" in f.sizes, f"from_keyword({text!r}): expected '8x10' in sizes, got {f.sizes}")


def test_multi_color_and_query():
    """Multi-color filter must produce $and (not $or) on the color field."""
    f = SearchFilters.from_keyword("red and ivory traditional rug", currency="INR")
    assert_true("red" in f.colors, f"Expected 'red' in colors, got {f.colors}")
    assert_true("ivory" in f.colors, f"Expected 'ivory' in colors, got {f.colors}")

    q = _build_query(
        "search.color.multi", f.colors, None, [], None, [], [],
        f.styles, None, [], [], [], [],
    )
    and_block = q.get("$and", [])
    color_clauses = [c for c in and_block if "search.color.multi" in c]
    assert_true(len(color_clauses) == 2, f"Expected 2 $and color clauses, got {color_clauses}")


def test_multi_style_and_query():
    """Multiple styles must produce $and (not $or) on the style field."""
    f = SearchFilters.from_params(styles=["modern", "geometric"], currency="INR")
    q = _build_query(
        None, [], None, [], None, [], [],
        f.styles, None, [], [], [], [],
    )
    and_block = q.get("$and", [])
    style_clauses = [c for c in and_block if "search.style" in c]
    assert_true(len(style_clauses) == 2, f"Expected 2 $and style clauses, got {style_clauses}")


def test_weight_filter_excludes_missing():
    from qlink_chatbot.utils.search_middleware import _weight_ok
    assert_true(_weight_ok(5.0, 6.0), "Weight 5 should pass ceiling of 6")
    assert_true(not _weight_ok(7.0, 6.0), "Weight 7 should fail ceiling of 6")
    assert_true(not _weight_ok(None, 6.0), "Missing weight must be excluded when ceiling is set")
    assert_true(not _weight_ok("", 6.0), "Empty weight must be excluded when ceiling is set")
    assert_true(not _weight_ok(0, 6.0), "Zero weight must be excluded when ceiling is set")


def test_blue_round_rugs_filter():
    f = SearchFilters.from_keyword("blue round rugs", currency="INR")
    assert_true("blue" in f.colors, f"Expected 'blue' in colors, got {f.colors}")
    assert_true("round" in f.shapes, f"Expected 'round' in shapes, got {f.shapes}")


def test_lightweight_rug_weight_filter():
    f = SearchFilters.from_keyword("lightweight rug under 6kg", currency="INR")
    assert_true(f.weight_filter == 6.0, f"Expected weight_filter=6.0, got {f.weight_filter}")


def test_usd_price_filter():
    f = SearchFilters.from_keyword("rugs under USD 500", currency="INR")
    assert_true(f.price_filter is not None, "Expected a price filter")
    assert_true(f.price_filter.get("currency") == "USD", f"Expected USD currency, got {f.price_filter}")
    assert_true(f.price_filter.get("max_amount") == 500.0, f"Expected max 500, got {f.price_filter}")


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
    test_size_normalization()
    test_multi_color_and_query()
    test_multi_style_and_query()
    test_weight_filter_excludes_missing()
    test_blue_round_rugs_filter()
    test_lightweight_rug_weight_filter()
    test_usd_price_filter()
    await test_live_mongo_optional()
    print("All product filter edge checks passed")


if __name__ == "__main__":
    asyncio.run(main())
