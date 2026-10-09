"""Single LLM entry point (Gemini). Falls back to canned output when no API key (mock mode)."""
import os, json, asyncio
from pathlib import Path
from dotenv import load_dotenv

for _env_path in (
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent / ".env.local",
    Path(__file__).resolve().parents[1] / ".env",
    Path(__file__).resolve().parents[1] / ".env.local",
):
    if _env_path.is_file():
        load_dotenv(_env_path)
MODEL = os.getenv("MODEL", "gemini-3.5-flash-lite")   # override via env, e.g. MODEL=gemini-2.5-pro
_client = None
_sem = asyncio.Semaphore(3)

def _api_key():
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=_api_key())
    return _client

async def complete(system: str, user: str, mock: str = "(mock output)", max_tokens: int = 4000) -> str:
    if not _api_key():
        await asyncio.sleep(0.3)  # fake latency so the UI feels alive
        return mock
    from google.genai import types
    async with _sem:
        for attempt in range(4):
            try:
                resp = await _get_client().aio.models.generate_content(
                    model=MODEL,
                    contents=user,
                    config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
                )
                return resp.text or ""
            except Exception:
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)

def parse_json(text: str):
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)
