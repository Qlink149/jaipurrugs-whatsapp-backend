"""
MongoDB product search internals: query builder, color scoring, deduplication, result formatting.
Consumed exclusively by search_middleware.py.
"""
import re
from urllib.parse import quote

from qlink_chatbot.database.mongo_base import db
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.utils.search_filters import CURRENCY_FIELDS, DEFAULT_CURRENCY, _normalize_name

products_collection = db["products"]
product_color_collection = db["product_color"]


def _color_match(color_text: str, requested: str) -> bool:
    text = str(color_text or "").lower().strip()
    req = str(requested or "").lower().strip()
    return bool(text and req and re.search(rf"(^|[^a-z]){re.escape(req)}([^a-z]|$)", text))


def _resolve_color_sku_scores(colors: list[str], limit: int = 1000) -> tuple[list[str], dict]:
    if not colors:
        return [], {}
    pattern = "|".join(
        rf"(^|[^a-z]){re.escape(c.lower().strip())}([^a-z]|$)" for c in colors if c
    )
    pipeline = [
        {"$project": {
            "sku": {"$ifNull": ["$SKU", "$sku"]},
            "color_raw": {"$ifNull": ["$PrimaryColorName", {"$ifNull": ["$Primary Color Name",
                         {"$ifNull": ["$ColorName", {"$ifNull": ["$color", "$Colour"]}]}]}]},
            "percentage": {"$ifNull": ["$ColorPercentage",
                          {"$ifNull": ["$Percentage", {"$ifNull": ["$percentage", 0]}]}]},
        }},
        {"$addFields": {
            "sku": {"$toUpper": {"$trim": {"input": {"$toString": {"$ifNull": ["$sku", ""]}}}}},
            "color": {"$toLower": {"$trim": {"input": {"$toString": {"$ifNull": ["$color_raw", ""]}}}}},
        }},
        {"$match": {"color": {"$regex": pattern}}},
        {"$group": {"_id": {"sku": "$sku", "color": "$color"},
                    "percentage": {"$sum": {"$ifNull": ["$percentage", 0]}}}},
        {"$group": {"_id": "$_id.sku", "total_percentage": {"$sum": "$percentage"},
                    "colors": {"$push": {"k": "$_id.color", "v": "$percentage"}}}},
        {"$sort": {"total_percentage": -1}},
        {"$limit": limit},
    ]
    aggregated = list(product_color_collection.aggregate(pipeline))
    ordered, scores = [], {}
    for row in aggregated:
        sku_val = (row.get("_id") or "").strip().upper()
        if not sku_val:
            continue
        color_map = {e["k"]: float(e.get("v", 0) or 0) for e in row.get("colors", []) if e.get("k")}
        if len(colors) > 1 and not all(any(_color_match(k, req) for k in color_map) for req in colors):
            continue
        matched = sum(v for k, v in color_map.items() if any(_color_match(k, req) for req in colors))
        if matched <= 0:
            continue
        ordered.append(sku_val)
        scores[sku_val] = {"total_percentage": matched, "colors": color_map}
    return ordered, scores


def _top_color_pct(color_map: dict, requested: list[str]) -> float:
    return max(
        (v for k, v in color_map.items() if any(_color_match(k, r) for r in requested)),
        default=0.0,
    )



def _build_query(
    color_field, colors, size_field, sizes, material_field, materials,
    constructions, styles, price_filter, generics, sku_filter, shapes,
    exclude_keys=None, currency_field=None,
) -> dict:
    q: dict = {"flags.inStock": True}
    and_clauses = []
    exclude_keys = [str(k).strip().upper() for k in (exclude_keys or []) if k]
    if exclude_keys:
        and_clauses.append({"$and": [
            {"SKU": {"$nin": exclude_keys}},
            {"BarCode": {"$nin": exclude_keys}},
            {"raw.SKU": {"$nin": exclude_keys}},
            {"raw.BarCode": {"$nin": exclude_keys}},
        ]})
    if color_field and colors:
        q[color_field] = {"$regex": "|".join(re.escape(c) for c in colors), "$options": "i"}
    if size_field and sizes:
        q[size_field] = {"$regex": "|".join(re.escape(s) for s in sizes), "$options": "i"}
    if material_field and materials:
        q[material_field] = {"$regex": "|".join(re.escape(m) for m in materials), "$options": "i"}
    if constructions:
        q["search.construction"] = {"$regex": "|".join(re.escape(c) for c in constructions), "$options": "i"}
    if styles:
        q["search.style"] = {"$regex": "|".join(re.escape(s) for s in styles), "$options": "i"}
    if shapes:
        q["search.shape"] = {"$regex": "|".join(re.escape(s) for s in shapes), "$options": "i"}
    if price_filter:
        min_a = price_filter.get("min_amount")
        max_a = price_filter.get("max_amount", price_filter.get("amount"))
        bounds = {"$gt": 0}
        if min_a is not None:
            bounds["$gte"] = min_a
        if max_a is not None:
            bounds["$lte"] = max_a
        if price_filter["currency"] == "INR":
            and_clauses.append({"$or": [{"search.price": bounds}, {"raw.INR_MRP": bounds}, {"INR_MRP": bounds}]})
        else:
            cf = CURRENCY_FIELDS.get(price_filter["currency"])
            if cf:
                and_clauses.append({"$or": [{f"raw.{cf}": bounds}, {cf: bounds}]})
    elif currency_field:
        and_clauses.append({"$or": [{f"raw.{currency_field}": {"$gt": 0}}, {currency_field: {"$gt": 0}}]})
    if sku_filter:
        and_clauses.append({"$or": [
            {"raw.SKU": {"$in": sku_filter}}, {"SKU": {"$in": sku_filter}},
            {"raw.BarCode": {"$in": sku_filter}}, {"BarCode": {"$in": sku_filter}},
        ]})
    if generics:
        regex = "|".join(re.escape(g) for g in generics)
        and_clauses.append({"$or": [
            {"raw.Name": {"$regex": regex, "$options": "i"}},
            {"raw.Collection": {"$regex": regex, "$options": "i"}},
            {"raw.Design": {"$regex": regex, "$options": "i"}},
            {"raw.Quality": {"$regex": regex, "$options": "i"}},
            {"raw.Shape": {"$regex": regex, "$options": "i"}},
        ]})
    if and_clauses:
        q["$and"] = and_clauses
    return q



def _sku(product: dict) -> str:
    raw = product.get("raw", product)
    for key in ("SKU", "BarCode"):
        v = product.get(key) or raw.get(key)
        if v:
            return str(v).strip().upper()
    return ""


def _dedupe_by_sku(products: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for p in products:
        key = _sku(p) or str(id(p))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _weight_ok(weight, ceiling: float) -> bool:
    try:
        return float(weight) <= ceiling
    except (TypeError, ValueError):
        return True



async def mongo_search(filters, currency: str, currency_field: str) -> list[dict]:
    """Execute the MongoDB product search and return formatted product dicts."""
    color_sku_filter: list[str] = []
    color_sku_scores: dict = {}
    query_colors = filters.colors[:]

    if filters.colors:
        color_sku_filter, color_sku_scores = _resolve_color_sku_scores(filters.colors)
        if color_sku_filter:
            query_colors = []

    color_fields = (
        ["search.color.single", "search.color.multi", None] if len(query_colors) == 1
        else ["search.color.multi", None] if len(query_colors) > 1
        else [None]
    )
    size_fields = ["search.size.exact", "search.size.group"] if filters.sizes else [None]
    material_fields = (
        ["search.material.primary", "search.material.family", "search.material.details", None]
        if filters.materials else [None]
    )

    results = []

    def _try_combos(sku_filter):
        for c_field in color_fields:
            if results:
                break
            for s_field in size_fields:
                if results:
                    break
                for m_field in material_fields:
                    q = _build_query(
                        c_field, query_colors, s_field, filters.sizes,
                        m_field, filters.materials, filters.constructions,
                        filters.styles, filters.price_filter, filters.generics,
                        sku_filter, filters.shapes, filters.exclude_keys, currency_field,
                    )
                    found = list(products_collection.find(q, {"_id": 0}).sort([("_id", 1)]).limit(200))
                    if found:
                        results.extend(found)
                        logger.info(f"MongoDB hit: {len(found)} [c={c_field} s={s_field} m={m_field}]")
                        break

    _try_combos(color_sku_filter)
    if not results and color_sku_filter:
        _try_combos([])

    if not results and filters.styles:
        q = _build_query(None, query_colors, None, filters.sizes, None, filters.materials,
                         filters.constructions, [], filters.price_filter,
                         filters.generics + filters.styles, color_sku_filter, filters.shapes,
                         filters.exclude_keys, currency_field)
        results = list(products_collection.find(q, {"_id": 0}).sort([("_id", 1)]).limit(200))
        if not results and color_sku_filter:
            q = _build_query(None, query_colors, None, filters.sizes, None, filters.materials,
                             filters.constructions, [], filters.price_filter,
                             filters.generics + filters.styles, [], filters.shapes,
                             filters.exclude_keys, currency_field)
            results = list(products_collection.find(q, {"_id": 0}).sort([("_id", 1)]).limit(200))

    if not results and (filters.price_filter or filters.weight_filter):
        q = _build_query(None, [], None, [], None, [], [], [], filters.price_filter, [], [],
                         filters.shapes, filters.exclude_keys, currency_field)
        results = list(products_collection.find(q, {"_id": 0}).sort([("_id", 1)]).limit(200))

    if not results and filters.generics and filters.has_any_filter():
        q = _build_query(None, query_colors, None, filters.sizes, None, filters.materials,
                         filters.constructions, filters.styles, filters.price_filter, [],
                         color_sku_filter, filters.shapes, filters.exclude_keys, currency_field)
        results = list(products_collection.find(q, {"_id": 0}).sort([("_id", 1)]).limit(200))
        if not results and color_sku_filter:
            q = _build_query(None, query_colors, None, filters.sizes, None, filters.materials,
                             filters.constructions, filters.styles, filters.price_filter, [],
                             [], filters.shapes, filters.exclude_keys, currency_field)
            results = list(products_collection.find(q, {"_id": 0}).sort([("_id", 1)]).limit(200))

    if not results and not filters.has_any_filter():
        q = _build_query(None, [], None, [], None, [], [], [], None, [], [], [],
                         filters.exclude_keys, currency_field)
        results = list(products_collection.find(q, {"_id": 0}).sort([("_id", 1)]).limit(200))

    if not results:
        return {"error": "No products found."}

    if filters.exclude_names:
        excluded = set(filters.exclude_names)
        results = [p for p in results if _normalize_name((p.get("raw") or p).get("Name")) not in excluded]
        if not results:
            return {"error": "No products found."}

    if filters.weight_filter is not None:
        results = [p for p in results if _weight_ok(p.get("search", {}).get("weight"), filters.weight_filter)]

    if color_sku_scores:
        results = sorted(
            results,
            key=lambda p: (
                _top_color_pct(color_sku_scores.get(_sku(p), {}).get("colors", {}), filters.colors),
                color_sku_scores.get(_sku(p), {}).get("total_percentage", 0),
            ),
            reverse=True,
        )

    unique = _dedupe_by_sku(results)
    selected = unique[:filters.limit]
    return _format_results(selected, currency, currency_field, filters.colors, color_sku_scores)



def _product_url(product_url: str, barcode: str) -> str:
    slug = str(product_url or "").strip()
    barcode = str(barcode or "").strip()
    if not slug:
        return ""
    if slug.startswith("http://") or slug.startswith("https://"):
        url = slug
    elif slug.startswith("/"):
        url = f"https://www.jaipurrugs.com{slug}"
    elif slug.startswith("in/rugs/") or slug.startswith("rugs/"):
        url = f"https://www.jaipurrugs.com/{slug}"
    else:
        url = f"https://www.jaipurrugs.com/in/rugs/{quote(slug, safe='/-')}"
    if barcode and "barcode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}barcode={quote(barcode, safe='')}"
    return url


def _format_results(
    products: list[dict], currency: str, currency_field: str,
    colors: list[str], color_sku_scores: dict,
) -> list[dict]:
    out = []
    for p in products:
        raw = p.get("raw", p)
        search = p.get("search", {})
        color = search.get("color", {})
        material = search.get("material", {})
        size = search.get("size", {})
        sku = _sku(p)
        score = color_sku_scores.get(sku, {})
        color_map = score.get("colors", {})
        highest_color = max(color_map, key=lambda k: color_map[k], default="") if color_map else ""
        barcode = p.get("BarCode") or raw.get("BarCode") or ""
        display_name = (
            raw.get("Name") or p.get("Name") or raw.get("Design") or p.get("Design")
            or raw.get("Collection") or p.get("Collection") or raw.get("GrColor") or sku
        )
        mrp = {cur: raw.get(f"{cur}_MRP") or p.get(f"{cur}_MRP") for cur in ("INR", "USD", "EUR", "GBP", "AUD", "CHF", "SGD", "AED")}
        image_raw = raw.get("HeadShot", "")
        out.append({
            "url": _product_url(raw.get("ProductURL") or p.get("ProductURL") or "", barcode),
            "price": {"currency": currency, "amount": raw.get(currency_field) or p.get(currency_field)},
            "name": display_name,
            "SKU": sku,
            "barcode": barcode,
            "collection": raw.get("Collection") or p.get("Collection") or "",
            "size": size.get("exact", raw.get("SizeInFT", "")),
            "shape": search.get("shape", raw.get("Shape", "")),
            "color": color.get("single", raw.get("GrColor", "")),
            "color_family": color.get("multi", raw.get("ColorFamily", "")),
            "matched_color_percentage": {
                "total": score.get("total_percentage", 0),
                "by_color": color_map,
                "highest": {"color": highest_color, "percentage": color_map.get(highest_color, 0.0)},
            },
            "style": search.get("style", raw.get("Style", "")),
            "construction": search.get("construction", raw.get("Construction", "")),
            "material": material.get("primary", raw.get("Material", "")),
            "fabric": material.get("details", raw.get("MaterialDetails", "")),
            "quality": search.get("quality", raw.get("Quality", "")),
            "room": search.get("room", [r.strip() for r in (raw.get("Room") or "").split(",") if r.strip()]),
            "weight": search.get("weight", raw.get("Weight", 0.0)),
            "image": image_raw.replace(" ", "%20") if image_raw else "",
            "mrp": mrp,
        })
    return out
