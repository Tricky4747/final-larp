"""OWNER: Person C. Web search + page fetch for the Validation agent.
Replace the mock bodies with a real provider (Tavily / SerpAPI / Brave / DuckDuckGo). Keep the signatures."""

async def web_search(query: str, n: int = 5) -> list[dict]:
    """Return [{"title": str, "url": str, "snippet": str}, ...]"""
    # TODO(C): real implementation
    return [{"title": f"Mock result {i} for '{query}'", "url": f"https://example.com/{i}",
             "snippet": "Competitor offers similar service at $40-60. Reviews complain about slow turnaround."}
            for i in range(n)]

async def fetch_page(url: str, max_chars: int = 6000) -> str:
    """Return cleaned page text, truncated to max_chars."""
    # TODO(C): httpx + readability/bs4
    return f"(mock page text for {url})"
