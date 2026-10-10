"""Shared LLM entry point with Apmix and Gemini providers."""

import asyncio
import json
import os
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

MODEL = os.getenv("MODEL", "gemini-3.5-flash-lite")
APMIX_BASE_URL = os.getenv("APMIX_BASE_URL", "https://api.apmix.ai/v1").rstrip("/")
APMIX_MODEL = os.getenv("APMIX_MODEL", "claude-sonnet-4-6-free")
_client = None
_apmix_client = None
_sem = asyncio.Semaphore(3)


def _provider() -> str | None:
    requested = os.getenv("LLM_PROVIDER", "").strip().lower()
    if requested:
        if requested not in {"apmix", "gemini"}:
            raise ValueError("LLM_PROVIDER must be 'apmix' or 'gemini'.")
        return requested
    return "gemini"


def is_configured() -> bool:
    """Return whether the selected LLM provider has a configured API key."""
    provider = _provider()
    if provider == "apmix":
        return bool(os.getenv("APMIX_API_KEY", "").strip())
    if provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip())
    return False


def _get_gemini_client():
    global _client
    if _client is None:
        from google import genai

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        _client = genai.Client(api_key=api_key)
    return _client


def _get_apmix_client():
    global _apmix_client
    if _apmix_client is None:
        from openai import AsyncOpenAI

        _apmix_client = AsyncOpenAI(
            api_key=os.environ["APMIX_API_KEY"],
            base_url=os.getenv("APMIX_BASE_URL", APMIX_BASE_URL).rstrip("/"),
        )
    return _apmix_client


async def complete(
    system: str,
    user: str,
    mock: str = "(mock output)",
    max_tokens: int = 4000,
) -> str:
    provider = _provider()
    if not is_configured():
        await asyncio.sleep(0.3)  # fake latency so the UI feels alive
        return mock

    async with _sem:
        for attempt in range(4):
            try:
                if provider == "apmix":
                    response = await _get_apmix_client().chat.completions.create(
                        model=os.getenv("APMIX_MODEL", APMIX_MODEL),
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        max_tokens=max_tokens,
                    )
                    return response.choices[0].message.content or ""

                from google.genai import types

                response = await _get_gemini_client().aio.models.generate_content(
                    model=MODEL,
                    contents=user,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        max_output_tokens=max_tokens,
                    ),
                )
                return response.text or ""
            except Exception:
                if attempt == 3:
                    raise
                await asyncio.sleep(2**attempt)


def parse_json(text: str):
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)
