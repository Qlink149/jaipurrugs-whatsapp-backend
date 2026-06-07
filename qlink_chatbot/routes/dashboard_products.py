"""
Dashboard product CRUD and catalog endpoints.
"""
import json
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile

from qlink_chatbot.database.mongo_base import whatsapp_sessions_collection
from qlink_chatbot.utils.jaipur_rugs_api import products_collection as website_products_collection

products_router = APIRouter()

manual_products_collection = whatsapp_sessions_collection.database["dashboard_products"]
catalog_designs_collection = whatsapp_sessions_collection.database["catalog_designs"]


def _jsonable(value):
    if isinstance(value, (ObjectId, datetime)):
        return str(value) if isinstance(value, ObjectId) else value.isoformat()
    if isinstance(value, list):
        return [_jsonable(i) for i in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def _product_doc(product: dict) -> dict:
    product = _jsonable(product)
    product["id"] = product.pop("_id", product.get("id"))
    product["source"] = product.get("source", "manual")
    return product


def _website_product_doc(product: dict) -> dict:
    raw = product.get("raw") or {}
    search = product.get("search") or {}
    material = search.get("material") or {}
    size = search.get("size") or {}
    barcode = raw.get("BarCode") or product.get("BarCode") or raw.get("SKU") or ""
    slug = raw.get("ProductURL") or ""
    name = raw.get("Name") or raw.get("Design") or raw.get("SKU") or "Jaipur Rugs Product"
    category = raw.get("Collection") or search.get("style") or ""
    image_urls = [u for u in [raw.get("HeadShot"), raw.get("Corner"), raw.get("CloseUp"), raw.get("Floorshot")] if u and not u.endswith("/")]
    return {
        "id": f"jr:{barcode or slug}",
        "source": "jaipur_rugs",
        "name": name,
        "type": raw.get("ProductType") or "Rugs",
        "category": category,
        "collection": category,
        "price": raw.get("INR_MRP") or search.get("price") or "",
        "buy_link": (f"https://www.jaipurrugs.com/in/rugs/{slug}?barcode={barcode}" if slug else ""),
        "description": raw.get("FullDescription") or raw.get("ShortDescription") or "",
        "location": "",
        "image_url": image_urls[0] if image_urls else "",
        "image_urls": image_urls,
        "baseTags": " | ".join(v for v in [category, search.get("style"), search.get("construction"), material.get("primary"), size.get("group")] if v),
        "sku": raw.get("SKU") or "",
        "barcode": barcode,
    }


@products_router.get("/products")
def list_products(skip: int = 0, limit: int = 100, q: str = ""):
    manual_query = {}
    website_query = {"flags.inStock": True}
    if q:
        manual_query = {"$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"type": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
        ]}
        website_query["$or"] = [
            {"raw.Name": {"$regex": q, "$options": "i"}},
            {"raw.Collection": {"$regex": q, "$options": "i"}},
            {"raw.Design": {"$regex": q, "$options": "i"}},
            {"raw.SKU": {"$regex": q, "$options": "i"}},
            {"raw.BarCode": {"$regex": q, "$options": "i"}},
            {"search.style": {"$regex": q, "$options": "i"}},
            {"search.material.primary": {"$regex": q, "$options": "i"}},
        ]

    manual_total = manual_products_collection.count_documents(manual_query)
    website_total = website_products_collection.count_documents(website_query)
    data = []
    remaining = limit
    website_skip = max(0, skip - manual_total)

    if skip < manual_total and remaining > 0:
        manual_data = [
            _product_doc(p)
            for p in manual_products_collection.find(manual_query).sort("updated_at", -1).skip(skip).limit(remaining)
        ]
        data.extend(manual_data)
        remaining -= len(manual_data)

    if remaining > 0:
        data.extend([
            _website_product_doc(p)
            for p in website_products_collection.find(website_query, {"_id": 0}).sort("raw.ModifyDate", -1).skip(website_skip).limit(remaining)
        ])

    return {"data": data, "meta": {"total": manual_total + website_total}}


@products_router.post("/products")
async def create_product(
    name: str = Form(...), type: str = Form(""), category: str = Form(""),
    price: str = Form(""), buy_link: str = Form(""), description: str = Form(""),
    location: str = Form(""), image: UploadFile | None = File(None),
):
    now = datetime.utcnow()
    doc = {
        "name": name, "type": type, "category": category, "price": price,
        "buy_link": buy_link, "description": description, "location": location,
        "image_url": "", "image_filename": image.filename if image else "",
        "created_at": now, "updated_at": now,
    }
    result = manual_products_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return {"data": _product_doc(doc)}


@products_router.patch("/products/{product_id}")
async def update_product(
    product_id: str, name: str = Form(...), type: str = Form(""), category: str = Form(""),
    price: str = Form(""), buy_link: str = Form(""), description: str = Form(""),
    location: str = Form(""), image: UploadFile | None = File(None),
):
    if product_id.startswith("jr:"):
        raise HTTPException(status_code=400, detail="Website products are read-only.")
    update = {
        "name": name, "type": type, "category": category, "price": price,
        "buy_link": buy_link, "description": description, "location": location,
        "updated_at": datetime.utcnow(),
    }
    if image:
        update["image_filename"] = image.filename
    manual_products_collection.update_one({"_id": ObjectId(product_id)}, {"$set": update})
    product = manual_products_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"data": _product_doc(product)}


@products_router.delete("/products/{product_id}")
def delete_product(product_id: str):
    if product_id.startswith("jr:"):
        raise HTTPException(status_code=400, detail="Website products are read-only.")
    result = manual_products_collection.delete_one({"_id": ObjectId(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"success": True}


@products_router.post("/catalog/upload")
async def upload_catalog(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON catalog") from exc
    items = data if isinstance(data, list) else data.get("designs") or data.get("products") or []
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Catalog JSON must contain a list")
    catalog_designs_collection.delete_many({})
    docs = []
    for item in (i for i in items if isinstance(i, dict)):
        docs.append({
            "designId": str(item.get("designId") or item.get("id") or ObjectId()),
            "name": item.get("name") or item.get("designName") or item.get("title") or "Untitled",
            "category": item.get("category") or item.get("collection") or "",
            "description": item.get("description") or "",
            "image_url": item.get("image_url") or item.get("image") or "",
            "buy_link": item.get("buy_link") or item.get("url") or "",
            "raw": item,
            "updated_at": datetime.utcnow(),
        })
    if docs:
        catalog_designs_collection.insert_many(docs)
    return {"designs": len(docs)}


@products_router.get("/catalog/search")
def search_catalog(q: str, limit: int = 5):
    query = {"$or": [
        {"name": {"$regex": q, "$options": "i"}},
        {"category": {"$regex": q, "$options": "i"}},
        {"description": {"$regex": q, "$options": "i"}},
    ]}
    results = [_jsonable(item) for item in catalog_designs_collection.find(query).limit(limit)]
    return {
        "results": results,
        "catalog_reply": {
            "type": "design" if results else "no_match",
            "reply_text": results[0]["name"] if results else "No catalog match found.",
            "images": [item.get("image_url") for item in results if item.get("image_url")],
            "documents": [],
        },
        "source_tree_matches": results,
    }


@products_router.put("/catalog/designs/{design_id}/recommendation")
def save_catalog_recommendation(design_id: str, payload: dict = Body(...)):
    result = catalog_designs_collection.update_one(
        {"designId": design_id},
        {"$set": {"description": payload.get("description", ""), "updated_at": datetime.utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Catalog design not found")
    return {"success": True}


@products_router.delete("/catalog/designs/{design_id}/recommendation")
def delete_catalog_recommendation(design_id: str):
    catalog_designs_collection.update_one(
        {"designId": design_id},
        {"$set": {"description": "", "updated_at": datetime.utcnow()}},
    )
    return {"success": True}
