"""
WhatsApp channel renderer.

Converts raw assistant markdown text into a list of WhatsApp message dicts
that can be dispatched via Gupshup.  Each dict has one of:
  {"type": "text", "text": "..."}
  {"type": "image", "image_url": "...", "caption": "..."}
  {"type": "interactive_cta", "image_url"?: "...", "button_url": "...",
                               "caption": "...", "button_text": "..."}

These functions were previously defined inside whatsapp_routes.py.
whatsapp_routes.py now imports them from here so existing import paths
(e.g. in test files) continue to work via a re-export shim there.
"""
import re

_IMAGE_MD_RE = re.compile(r'!\[.*?\]\((https?://\S+?)\)')
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')


def _extract_cta(caption: str) -> tuple[str, str | None]:
    """Pull the first [View Product](...) markdown link out of caption.

    Returns (cleaned_caption, product_url) or (caption, None).
    """
    for match in _MD_LINK_RE.finditer(caption):
        label, url = match.group(1), match.group(2)
        if "view product" in label.lower() or "jaipurrugs.com/in/rugs" in url:
            cleaned = _MD_LINK_RE.sub("", caption, count=1).strip()
            cleaned = re.sub(r'(?m)^\s*[-·•]\s*$', '', cleaned)
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
            return cleaned, url
    return caption, None


def _extract_search_cta(text: str) -> tuple[str, str | None, str | None]:
    """Pull the first search/browse markdown link out of a text block.

    Returns (cleaned_text, search_url, button_label) or (text, None, None).
    """
    for match in _MD_LINK_RE.finditer(text):
        label, url = match.group(1), match.group(2)
        if "search" in label.lower() or "browse" in label.lower() or "/search" in url:
            cleaned = _MD_LINK_RE.sub("", text, count=1).strip()
            cleaned = re.sub(r'(?m)^\s*[-·•]\s*$', '', cleaned)
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
            btn_label = re.sub(r'[^\w\s]', '', label).strip() or "Search More Rugs"
            return cleaned, url, btn_label
    return text, None, None


def _clean_for_whatsapp(text: str) -> str:
    """Convert markdown formatting to WhatsApp-compatible text and strip artifacts."""
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    text = re.sub(r'(?m)^\s*[\*_]{1,3}\s*$', '', text)
    text = re.sub(r'[\*_]+\s*$', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _build_whatsapp_responses(text: str) -> list[dict]:
    """Split bot text into WhatsApp messages.

    Blocks with an image + View Product URL become interactive_cta messages.
    Blocks without an image are batched into text messages.
    """
    blocks = [b.strip() for b in re.split(r'\n\n+', text.strip()) if b.strip()]
    responses: list[dict] = []
    pending_text: list[str] = []
    deferred_search_cta: dict | None = None
    seen_product_urls: set[str] = set()

    for block in blocks:
        match = _IMAGE_MD_RE.search(block)
        if match:
            if pending_text:
                responses.append({"type": "text", "text": "\n\n".join(pending_text)})
                pending_text = []
            image_url = match.group(1)
            caption = _IMAGE_MD_RE.sub("", block)
            caption = re.sub(r'(?m)^\s*[-·•]\s*$', '', caption)
            caption = re.sub(r'\n\s*[-·•]\s*$', '', caption).strip()
            caption = _clean_for_whatsapp(caption)
            caption, product_url = _extract_cta(caption)
            caption = re.sub(r'(?m)^\s*[-·•·]\s*[\*_]*\s*$', '', caption)
            caption = _clean_for_whatsapp(caption)
            if product_url and product_url not in seen_product_urls:
                seen_product_urls.add(product_url)
                responses.append({
                    "type": "interactive_cta",
                    "image_url": image_url,
                    "button_url": product_url,
                    "caption": caption or "Tap below to view this rug on Jaipur Rugs.",
                    "button_text": "View Product",
                })
            else:
                responses.append({"type": "image", "image_url": image_url, "caption": caption})
        else:
            cleaned, search_url, btn_label = _extract_search_cta(block)
            if search_url:
                if cleaned:
                    pending_text.append(cleaned)
                deferred_search_cta = {
                    "type": "interactive_cta",
                    "button_url": search_url,
                    "caption": "Tap below to browse more rugs.",
                    "button_text": btn_label,
                }
            else:
                block_text = _clean_for_whatsapp(block)
                block_text, product_url = _extract_cta(block_text)
                if product_url and product_url not in seen_product_urls:
                    if pending_text:
                        responses.append({"type": "text", "text": "\n\n".join(pending_text)})
                        pending_text = []
                    seen_product_urls.add(product_url)
                    responses.append({
                        "type": "interactive_cta",
                        "button_url": product_url,
                        "caption": block_text or "Tap below to view this rug on Jaipur Rugs.",
                        "button_text": "View Product",
                    })
                else:
                    block_text = re.sub(
                        r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'\2', block_text
                    )
                    pending_text.append(block_text)

    if pending_text:
        responses.append({"type": "text", "text": "\n\n".join(pending_text)})

    if deferred_search_cta:
        responses.append(deferred_search_cta)

    return responses or [{"type": "text", "text": text}]


def _has_product_send(responses: list[dict]) -> bool:
    product_response_types = {"image", "interactive_cta", "product_template", "text_with_image"}
    return any(
        isinstance(r, dict) and r.get("type") in product_response_types
        for r in responses
    )
