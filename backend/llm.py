"""Single LLM entry point. Falls back to canned output when no API key (mock mode)."""
import os, json, asyncio

MODEL = os.getenv("MODEL", "claude-sonnet-4-6")
_client = None

def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic()
    return _client

async def complete(system: str, user: str, mock: str = "(mock output)", max_tokens: int = 2000) -> str:
    if not os.getenv("ANTHROPIC_API_KEY"):
        await asyncio.sleep(0.3)  # fake latency so the UI feels alive
        return mock
    resp = await _get_client().messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")

def parse_json(text: str):
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)
