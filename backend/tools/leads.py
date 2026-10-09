"""OWNER: Person D. Find leads from a SAFE public source (Google Places / public directory / Apollo-style API)."""

async def find_leads(query: str, location: str, n: int = 20) -> list[dict]:
    """Return [{"name","handle","contact","source","why"}, ...]. handle = username/email to message."""
    # TODO(D): real implementation. Avoid scraping logged-in social platforms.
    return [{"name": f"Lead {i}", "handle": f"@lead{i}", "contact": f"lead{i}@example.com",
             "source": "mock", "why": "Small local business, no website"} for i in range(n)]
