"""OWNER: Person D. Send DMs and read replies. Default = SANDBOX: send only to test accounts you control."""

async def send_dm(lead: dict, text: str) -> dict:
    """Send one message. Return {"ok": bool, "id": str}."""
    # TODO(D): Telegram bot / email / test Instagram account. Real sends must only target test accounts in the demo.
    return {"ok": True, "id": f"mock-{lead.get('handle')}"}

async def poll_replies() -> list[dict]:
    """Return NEW replies since last call: [{"handle": str, "variant": str, "text": str}, ...]"""
    # TODO(D): read inbox/bot updates. Variant is tracked by whoever sent (see Control.run_round).
    return []
