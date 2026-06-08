"""Web channel renderer — wraps raw assistant text in a WebSocket message dict."""


def render_web_response(content: str) -> dict:
    """Return a WebSocket message payload for the given assistant text."""
    return {
        "type": "message",
        "from": "assistant",
        "content": content or "Error generating response.",
    }
