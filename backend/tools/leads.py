"""Find businesses via web search and collect the contact emails they publish on their own sites.

Pipeline: search -> drop directories/social -> visit homepage + contact/about pages
-> extract emails -> keep leads that have one -> merge into leads.json.

Search backend, first one configured wins (keys are read from the environment or a .env file):
  1. TAVILY_API_KEY -> Tavily Search API
  2. BRAVE_API_KEY  -> Brave Search API
  3. otherwise      -> DuckDuckGo via the `ddgs` package (pip install ddgs; rate limited)
If the chosen API fails or returns nothing, the next backend is tried.
"""

import asyncio
import json
import logging
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

RESULTS_FILE = Path(__file__).with_name("leads.json")
REQUEST_TIMEOUT_SECONDS = 12
MAX_PAGE_BYTES = 1_500_000
MAX_CONTACT_PAGES = 2
WORKERS = 8
USER_AGENT = "Mozilla/5.0 (compatible; leadgen-bot/1.0)"
logger = logging.getLogger(__name__)

# Directories, social networks and aggregators: they rarely expose the business's own email.
SKIP_DOMAINS = {
    "practo.com", "justdial.com", "sulekha.com", "lybrate.com", "credihealth.com",
    "indiamart.com", "tradeindia.com", "yellowpages.com", "yelp.com", "tripadvisor.com",
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "pinterest.com", "quora.com", "reddit.com", "wikipedia.org",
    "google.com", "maps.google.com", "apple.com", "bing.com", "medium.com",
    "timesofindia.com", "thehindu.com", "magicbricks.com", "99acres.com",
}
JUNK_EMAIL_DOMAINS = {
    "example.com", "domain.com", "email.com", "yoursite.com", "mysite.com",
    "sentry.io", "wixpress.com", "sentry-next.wixpress.com", "godaddy.com",
}
JUNK_EMAIL_LOCALS = {"example", "you", "your", "name", "email", "yourname", "user", "username", "test", "johndoe"}
FILE_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "css", "js", "woff", "woff2", "ico", "pdf"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
AT_RE = re.compile(r"\s*[\[\(\{]\s*at\s*[\]\)\}]\s*", re.I)
DOT_RE = re.compile(r"\s*[\[\(\{]\s*dot\s*[\]\)\}]\s*", re.I)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#]+)""", re.I)
CONTACT_HINT_RE = re.compile(r"contact|about|reach|appointment|enquir|inquir", re.I)


class LeadSearchError(RuntimeError):
    """Raised when no search backend is usable."""


def _load_env() -> None:
    """Load KEY=VALUE lines from .env / .env.local without overriding real env vars."""
    search_dirs = [
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve().parents[2],
        Path.cwd(),
    ]
    seen_files = set()
    for directory in search_dirs:
        for fname in (".env", ".env.local"):
            env_file = directory / fname
            if env_file in seen_files or not env_file.is_file():
                continue
            seen_files.add(env_file)
            try:
                lines = env_file.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                value = value.strip().strip("'\"").strip()
                if key and value:
                    os.environ.setdefault(key, value)


_load_env()


# ---------------------------------------------------------------- search

def _tavily_search(query: str, api_key: str) -> list[dict[str, str]]:
    body = json.dumps(
        {
            "query": query,
            "search_depth": "basic",
            "max_results": 20,
            "exclude_domains": sorted(SKIP_DOMAINS),
        }
    ).encode()
    request = Request(
        "https://api.tavily.com/search",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS * 2) as response:
            data = json.loads(response.read())
    except Exception as exc:  # bad key, quota, network: caller falls back to another backend
        logger.warning("Tavily search failed for %r: %s", query, exc)
        return []
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ]


def _brave_search(query: str, pages: int, api_key: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for page in range(pages):
        url = f"https://api.search.brave.com/res/v1/web/search?q={quote(query)}&count=20&offset={page}"
        request = Request(
            url,
            headers={"Accept": "application/json", "X-Subscription-Token": api_key, "User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read())
        except Exception as exc:  # network/HTTP/JSON: stop paging, keep what we have
            logger.warning("Brave search failed for %r (page %d): %s", query, page, exc)
            break
        results = data.get("web", {}).get("results", [])
        if not results:
            break
        out.extend(
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
            for r in results
        )
    return out


def _ddg_search(query: str, max_results: int) -> list[dict[str, str]]:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError as exc:
            raise LeadSearchError(
                "No search backend available: set TAVILY_API_KEY (or BRAVE_API_KEY) in .env, or pip install ddgs."
            ) from exc
    try:
        rows = DDGS().text(query, max_results=max_results)
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for %r: %s", query, exc)
        return []
    return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in rows]


def _search(query: str) -> list[dict[str, str]]:
    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if tavily_key:
        results = _tavily_search(query, tavily_key)
        if results:
            return results
    brave_key = os.environ.get("BRAVE_API_KEY", "").strip()
    if brave_key:
        results = _brave_search(query, pages=3, api_key=brave_key)
        if results:
            return results
    if tavily_key or brave_key:
        # If API keys are configured but returned 0 results, try DDG only if available
        try:
            return _ddg_search(query, max_results=40)
        except LeadSearchError:
            return []
    return _ddg_search(query, max_results=40)


# ---------------------------------------------------------------- fetching

def _fetch(url: str, *, html_only: bool = True) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.5"})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            if html_only and "html" not in content_type:
                return ""
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read(MAX_PAGE_BYTES).decode(charset, errors="replace")
    except Exception:  # scraping: any failure just means "no page"
        return ""


def _allowed_by_robots(url: str, cache: dict[str, RobotFileParser]) -> bool:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    parser = cache.get(base)
    if parser is None:
        parser = RobotFileParser()
        parser.parse(_fetch(f"{base}/robots.txt", html_only=False).splitlines())  # empty => allow all
        cache[base] = parser
    return parser.can_fetch(USER_AGENT, url)


# ---------------------------------------------------------------- extraction

def _extract_emails(raw: str) -> list[str]:
    text = unescape(raw).replace("%40", "@")
    text = AT_RE.sub("@", text)
    text = DOT_RE.sub(".", text)
    found: list[str] = []
    for match in EMAIL_RE.findall(text):
        email = match.strip(".").lower()
        local, _, domain = email.partition("@")
        if domain.rsplit(".", 1)[-1] in FILE_TLDS:
            continue
        if domain in JUNK_EMAIL_DOMAINS or domain.endswith("sentry.io") or domain.endswith("wixpress.com"):
            continue
        if local in JUNK_EMAIL_LOCALS:
            continue
        if email not in found:
            found.append(email)
    return found


def _contact_links(raw: str, base_url: str) -> list[str]:
    host = urlparse(base_url).netloc
    links: list[str] = []
    for href in HREF_RE.findall(raw):
        if href.startswith(("mailto:", "tel:", "javascript:")) or not CONTACT_HINT_RE.search(href):
            continue
        absolute = urljoin(base_url, unescape(href))
        if urlparse(absolute).netloc == host and absolute not in links:
            links.append(absolute)
    return links


def _same_site(email: str, host: str) -> bool:
    domain = email.split("@", 1)[1]
    host = host.removeprefix("www.")
    return domain == host or domain.endswith("." + host) or host.endswith("." + domain)


def _scan_site(result: dict[str, str], robots: dict[str, RobotFileParser]) -> list[str]:
    parsed = urlparse(result["url"])
    host = parsed.netloc
    root = f"{parsed.scheme}://{host}/"
    pages = [root]
    if result["url"].rstrip("/") != root.rstrip("/"):
        pages.append(result["url"])

    emails: list[str] = []
    contact_pages: list[str] = []
    for index, page in enumerate(pages):
        if not _allowed_by_robots(page, robots):
            continue
        raw = _fetch(page)
        emails.extend(e for e in _extract_emails(raw) if e not in emails)
        if index == 0:
            contact_pages = _contact_links(raw, root)[:MAX_CONTACT_PAGES]
            if not contact_pages:
                contact_pages = [urljoin(root, "contact"), urljoin(root, "contact-us")][:MAX_CONTACT_PAGES]
    for page in contact_pages:
        if emails and len(emails) >= 3:
            break
        if page in pages or not _allowed_by_robots(page, robots):
            continue
        emails.extend(e for e in _extract_emails(_fetch(page)) if e not in emails)

    # Emails on the business's own domain first, then gmail/yahoo/etc. listed on the page.
    return sorted(emails, key=lambda e: not _same_site(e, host))


# ---------------------------------------------------------------- orchestration

def _domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _is_skipped(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in SKIP_DOMAINS)


def _clean_name(title: str, domain: str) -> str:
    name = re.split(r"\s[|\-–—:]\s", unescape(title).strip())[0].strip()
    return name or domain


def _load_existing() -> list[dict[str, str]]:
    try:
        data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_results(results: list[dict[str, str]]) -> None:
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=RESULTS_FILE.parent, prefix=f".{RESULTS_FILE.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(results, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(tmp, RESULTS_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _discover(query: str, location: str, n: int) -> list[dict[str, str]]:
    queries = [
        f"{query} in {location}",
        f"{query} {location} contact email",
        f"{query} {location} official website contact us",
    ]
    candidates: dict[str, dict[str, str]] = {}
    for q in queries:
        for row in _search(q):
            url = row.get("url", "")
            if not url.startswith(("http://", "https://")):
                continue
            domain = _domain_of(url)
            if domain and not _is_skipped(domain) and domain not in candidates:
                candidates[domain] = row
        if len(candidates) >= n * 5:
            break
    if not candidates:
        return []

    existing = _load_existing()
    known_emails = {e.strip().lower() for lead in existing for e in lead.get("contact", "").split(",") if e.strip()}
    robots: dict[str, RobotFileParser] = {}
    new_leads: list[dict[str, str]] = []

    executor = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        futures = {executor.submit(_scan_site, row, robots): (domain, row) for domain, row in candidates.items()}
        for future in as_completed(futures):
            domain, row = futures[future]
            try:
                emails = future.result()
            except Exception as exc:
                logger.warning("Scan failed for %s: %s", domain, exc)
                continue
            emails = [e for e in emails if e not in known_emails]
            if not emails:
                continue
            known_emails.update(emails)
            new_leads.append(
                {
                    "name": _clean_name(row.get("title", ""), domain),
                    "handle": domain,
                    "contact": ", ".join(emails[:3]),
                    "source": row["url"],
                    "why": f"Matched web search for '{query}' in {location}; email published on {domain}.",
                }
            )
            if len(new_leads) >= n:
                break
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if new_leads:
        _save_results(existing + new_leads)
    return new_leads


async def find_leads(query: str, location: str, n: int = 20) -> list[dict[str, str]]:
    """Search the web for `query` businesses in `location` and return those with a published email.

    Each dict has name, handle (domain), contact (comma-separated emails), source (URL), why.
    New leads are merged into leads.json beside this module (de-duplicated by email).
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be non-empty text.")
    if not isinstance(location, str) or not location.strip():
        raise ValueError("location must be non-empty text.")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("n must be a positive integer.")
    return await asyncio.to_thread(_discover, query.strip(), location.strip(), n)