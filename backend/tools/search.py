
"""Web search and webpage fetching for the Validation agent."""

import asyncio
import ipaddress
import logging
import os
from urllib.parse import urlparse

from llm import is_configured

logger = logging.getLogger(__name__)


def _mock_mode() -> bool:
    """Keep the pipeline runnable without API keys."""
    setting = os.getenv("ENABLE_LIVE_SEARCH")

    if setting is not None:
        return setting.strip().lower() not in {
            "1", "true", "yes", "on"
        }

    return not is_configured()


async def web_search(query: str, n: int = 5) -> list[dict]:
    """Return search results with title, URL, and snippet."""

    if not query.strip() or n <= 0:
        return []

    # Explicit placeholder results keep mock-mode demos working.
    if _mock_mode():
        return [{
            "title": "MOCK MODE: Live search not performed",
            "url": "https://example.com/",
            "snippet": (
                "Placeholder only. No real competitor research "
                "was performed. Enable live search to retrieve "
                "actual sources."
            ),
        }]

    try:
        from ddgs import DDGS

        # DDGS is synchronous, so run it in a worker thread.
        results = await asyncio.to_thread(
            lambda: DDGS(timeout=8).text(
                query,
                max_results=min(n, 10),
            )
        )

        cleaned_results = []

        for result in results or []:
            title = str(result.get("title") or "").strip()
            url = str(
                result.get("href") or result.get("url") or ""
            ).strip()
            snippet = str(
                result.get("body") or result.get("snippet") or ""
            ).strip()

            if not url.startswith(("https://", "http://")):
                continue

            cleaned_results.append({
                "title": title or "Untitled result",
                "url": url,
                "snippet": snippet,
            })

        return cleaned_results[:n]

    except Exception as exc:
        # A failed search should not crash the whole pipeline.
        logger.warning("Web search failed: %s", exc)
        return []


async def fetch_page(url: str, max_chars: int = 6000) -> str:
    """Fetch a public webpage and return its readable text."""

    if not url or max_chars <= 0:
        return ""

    if _mock_mode():
        return (
            "MOCK MODE: No webpage was fetched. "
            "This is not real research."
        )

    # Only allow ordinary web URLs, not local machine addresses.
    try:
        parsed = urlparse(url.strip())
        hostname = parsed.hostname or ""

        if parsed.scheme not in {"http", "https"} or not hostname:
            return ""

        if parsed.username or parsed.password:
            return ""

        if hostname.lower() == "localhost" or hostname.lower().endswith(
            ".localhost"
        ):
            return ""

        try:
            address = ipaddress.ip_address(hostname)
            if (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_reserved
            ):
                return ""
        except ValueError:
            # A normal domain name is not an IP address.
            pass

        import httpx
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "CrewDesk-Research/1.0"
        }

        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get(
            "content-type", ""
        ).lower()

        if content_type and not any(
            kind in content_type
            for kind in ("text/html", "application/xhtml+xml")
        ):
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove elements that usually aren't useful for research.
        for tag in soup.find_all(
            ["script", "style", "noscript", "svg", "iframe", "form", "nav"]
        ):
            tag.decompose()

        title = (
            soup.title.get_text(" ", strip=True)
            if soup.title
            else ""
        )

        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.body
            or soup
        )

        text = " ".join(main_content.stripped_strings)

        if title and title.lower() not in text[:len(title) + 10].lower():
            text = f"{title}\n{text}"

        return text[:max_chars]

    except Exception as exc:
        # Some sites block automated requests. Treat that as a
        # failed fetch rather than failing the entire agent run.
        logger.warning("Page fetch failed for %s: %s", url, exc)
        return ""
