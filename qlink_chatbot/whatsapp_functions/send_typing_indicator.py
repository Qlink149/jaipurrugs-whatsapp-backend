import asyncio


async def send_typing_indicator(phone_number: str) -> None:
    """No-op placeholder.

    Gupshup was rendering the attempted typing notification payload as a normal
    WhatsApp message, so keep this disabled until a supported typing API is used.
    """
    _ = phone_number


async def typing_indicator_loop(phone_number: str, stop_event: asyncio.Event) -> None:
    """Wait for completion without sending a visible WhatsApp message."""
    _ = phone_number
    await stop_event.wait()
