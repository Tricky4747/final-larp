"""Discover public career-guidance posts from configurable Reddit RSS feeds."""

import asyncio
import html
import json
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

SOURCES_FILE = Path(__file__).with_name("lead_sources.json")
RESULTS_FILE = Path(__file__).with_name("leads.json")
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = "final-larp-leadgen/1.0 (public RSS feed reader)"
ATOM_NAMESPACE = "{http://www.w3.org/2005/Atom}"
logger = logging.getLogger(__name__)


class LeadSearchError(RuntimeError):
    """Raised when Reddit source configuration or all configured feeds fail."""


class LeadSourceUnavailable(LeadSearchError):
    """Raised when no configured public RSS feed could be read."""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(value)
    return " ".join(html.unescape(" ".join(extractor.parts)).split())


def _load_sources() -> dict[str, Any]:
    try:
        config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LeadSearchError(f"Cannot load Reddit feed settings from {SOURCES_FILE}.") from exc
    if not isinstance(config, dict):
        raise LeadSearchError("Reddit feed settings must be a JSON object.")

    subreddits = config.get("subreddits")
    intent_terms = config.get("intent_terms")
    topic_terms = config.get("topic_terms")
    limit_per_feed = config.get("limit_per_feed")
    if (
        not isinstance(subreddits, list)
        or not subreddits
        or any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_]+", item) for item in subreddits)
    ):
        raise LeadSearchError("'subreddits' must be a non-empty list of subreddit names.")
    for field, terms in (("intent_terms", intent_terms), ("topic_terms", topic_terms)):
        if (
            not isinstance(terms, list)
            or not terms
            or any(not isinstance(term, str) or not term.strip() for term in terms)
        ):
            raise LeadSearchError(f"'{field}' must be a non-empty list of text terms.")
    if isinstance(limit_per_feed, bool) or not isinstance(limit_per_feed, int) or limit_per_feed < 1:
        raise LeadSearchError("'limit_per_feed' must be a positive integer.")
    return config


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", text, re.IGNORECASE) for term in terms)


def _read_feed(subreddit: str, opener: Callable[..., Any]) -> list[dict[str, str]]:
    url = f"https://www.reddit.com/r/{quote(subreddit, safe='')}/new/.rss"
    request = Request(
        url,
        headers={"Accept": "application/atom+xml, application/xml", "User-Agent": USER_AGENT},
    )
    try:
        with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            root = ET.fromstring(response.read())
    except HTTPError as exc:
        raise LeadSearchError(f"Reddit feed r/{subreddit} returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise LeadSearchError(
            f"Could not read Reddit feed r/{subreddit} ({type(exc).__name__})."
        ) from exc
    except ET.ParseError as exc:
        raise LeadSearchError(f"Reddit feed r/{subreddit} returned invalid XML.") from exc

    entries: list[dict[str, str]] = []
    for entry in root.findall(f"{ATOM_NAMESPACE}entry"):
        title_node = entry.find(f"{ATOM_NAMESPACE}title")
        content_node = entry.find(f"{ATOM_NAMESPACE}content")
        summary_node = entry.find(f"{ATOM_NAMESPACE}summary")
        link_node = entry.find(f"{ATOM_NAMESPACE}link")
        author_node = entry.find(f"{ATOM_NAMESPACE}author/{ATOM_NAMESPACE}name")
        if title_node is None or link_node is None:
            continue
        title = _plain_text("".join(title_node.itertext()))
        content_node = content_node if content_node is not None else summary_node
        content = (
            _plain_text("".join(content_node.itertext()))
            if content_node is not None
            else ""
        )
        link = link_node.attrib.get("href", "").strip()
        author = _plain_text("".join(author_node.itertext())) if author_node is not None else ""
        if title and link.startswith("https://www.reddit.com/"):
            entries.append({"title": title, "content": content, "url": link, "author": author})
    return entries


def _save_results(results: list[dict[str, str]]) -> None:
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=RESULTS_FILE.parent,
            prefix=f".{RESULTS_FILE.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            json.dump(results, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, RESULTS_FILE)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _discover_leads(
    query: str,
    location: str,
    limit: int,
    *,
    opener: Callable[..., Any] = urlopen,
) -> list[dict[str, str]]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty text.")
    if not isinstance(location, str) or not location.strip():
        raise ValueError("location must be non-empty text.")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer.")

    config = _load_sources()
    successful_feeds = 0
    failures: list[str] = []
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for subreddit in config["subreddits"]:
        try:
            posts = _read_feed(subreddit, opener)
            successful_feeds += 1
        except LeadSearchError as exc:
            failures.append(str(exc))
            logger.warning("%s", exc)
            continue

        for post in posts[: config["limit_per_feed"]]:
            searchable_text = f"{post['title']} {post['content']}"
            if not _contains_any(searchable_text, config["intent_terms"]):
                continue
            if not _contains_any(searchable_text, config["topic_terms"]):
                continue
            if post["url"] in seen_urls:
                continue
            seen_urls.add(post["url"])
            results.append(
                {
                    "name": post["title"],
                    "handle": post["author"],
                    "contact": "",
                    "source": post["url"],
                    "why": (
                        f"Public Reddit post in r/{subreddit} contains language "
                        "seeking advice and mentions career or skill development."
                    ),
                }
            )
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break

    if successful_feeds == 0:
        detail = "; ".join(failures) if failures else "No feeds were configured."
        raise LeadSourceUnavailable(f"No Reddit feeds could be read. {detail}")
    _save_results(results)
    return results


async def find_leads(query: str, location: str, n: int = 20) -> list[dict[str, str]]:
    """Return public Reddit posts matching configured career-guidance terms.

    ``query`` and ``location`` remain required for compatibility with the
    backend agent interface; edit ``lead_sources.json`` to select feeds and
    matching terms. Reddit handles are included only when the feed publishes
    them. This function never extracts personal email addresses. Each
    successful search atomically replaces ``leads.json`` beside this module.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty text.")
    if not isinstance(location, str) or not location.strip():
        raise ValueError("location must be non-empty text.")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("n must be a positive integer.")
    try:
        return await asyncio.to_thread(
            _discover_leads, query.strip(), location.strip(), n
        )
    except LeadSourceUnavailable as exc:
        logger.warning("Lead discovery unavailable: %s", exc)
        return []
