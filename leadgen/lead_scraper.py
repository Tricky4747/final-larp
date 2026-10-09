"""Discover business prospects using Tavily's official Search API."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

API_ENDPOINT = "https://api.tavily.com/search"
MODULE_DIRECTORY = Path(__file__).resolve().parent
MAX_RESULTS = 20
REQUEST_TIMEOUT_SECONDS = 15
LEAD_FIELDS = {"name", "handle", "contact", "why", "where"}
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
SHARED_PROFILE_HOSTS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "x.com",
    "youtube.com",
}

logger = logging.getLogger(__name__)


class LeadSearchError(RuntimeError):
    """Raised when configuration or the permitted search source fails."""


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    working_directory_candidate = Path.cwd() / candidate
    if working_directory_candidate.exists():
        return working_directory_candidate
    if candidate.parent != Path(".") and working_directory_candidate.parent.exists():
        return working_directory_candidate
    return MODULE_DIRECTORY / candidate


def _validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        raise LeadSearchError("Configuration must be a JSON object.")
    required = {"business_idea", "target_customer", "location", "limit"}
    if set(config) != required:
        missing = sorted(required - set(config))
        extra = sorted(set(config) - required)
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected fields: {', '.join(extra)}")
        raise LeadSearchError(f"Invalid config ({'; '.join(details)}).")

    validated: dict[str, Any] = {}
    for field in ("business_idea", "target_customer", "location"):
        value = config[field]
        if not isinstance(value, str) or not value.strip():
            raise LeadSearchError(f"Config field '{field}' must be non-empty text.")
        validated[field] = value.strip()

    limit = config["limit"]
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
        raise LeadSearchError(f"Config field 'limit' must be an integer from 1 to {MAX_RESULTS}.")
    validated["limit"] = limit
    return validated


def _normalize_http_url(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text.")
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"{field} must be an absolute HTTP or HTTPS URL.")
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            parts.query,
            parts.fragment,
        )
    )


def validate_lead(lead: Mapping[str, Any]) -> dict[str, str]:
    """Validate a lead and return exactly the documented output fields."""
    if not isinstance(lead, Mapping) or set(lead) != LEAD_FIELDS:
        raise ValueError("A lead must contain exactly name, handle, contact, why, and where.")

    cleaned: dict[str, str] = {}
    for field in ("name", "handle", "contact", "why"):
        value = lead[field]
        if not isinstance(value, str):
            raise ValueError(f"Lead field '{field}' must be a string.")
        cleaned[field] = value.strip()

    if not cleaned["name"]:
        raise ValueError("Lead field 'name' must be non-empty.")
    if not cleaned["why"]:
        raise ValueError("Lead field 'why' must be non-empty.")
    if cleaned["contact"]:
        if "@" in cleaned["contact"] and "://" not in cleaned["contact"]:
            if not EMAIL_PATTERN.fullmatch(cleaned["contact"]):
                raise ValueError("Lead contact email is invalid.")
        else:
            cleaned["contact"] = _normalize_http_url(cleaned["contact"], "contact")
    if cleaned["handle"] and "://" in cleaned["handle"]:
        cleaned["handle"] = _normalize_http_url(cleaned["handle"], "handle")

    cleaned["where"] = _normalize_http_url(lead["where"], "where")
    return cleaned


def _normalized_domain(url: str) -> str:
    hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def _profile_key(value: str) -> str:
    if "://" in value:
        parts = urlsplit(value)
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/").lower(), "", "")
        )
    return value.strip().casefold().lstrip("@")


def _dedupe_keys(lead: Mapping[str, str]) -> set[str]:
    keys: set[str] = set()
    domain = _normalized_domain(lead["where"])
    if domain not in SHARED_PROFILE_HOSTS:
        keys.add(f"domain:{domain}")
    if lead["handle"]:
        keys.add(f"profile:{_profile_key(lead['handle'])}")
    if lead["contact"]:
        if "@" in lead["contact"] and "://" not in lead["contact"]:
            keys.add(f"email:{lead['contact'].casefold()}")
        else:
            keys.add(f"profile:{_profile_key(lead['contact'])}")
    if domain in SHARED_PROFILE_HOSTS and not lead["handle"]:
        keys.add(f"profile:{_profile_key(lead['where'])}")
    return keys


def deduplicate_leads(leads: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Validate leads and keep the first record for each domain/profile/email."""
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for lead in leads:
        cleaned = validate_lead(lead)
        keys = _dedupe_keys(cleaned)
        if keys & seen:
            continue
        seen.update(keys)
        unique.append(cleaned)
    return unique


def _search_request(
    query: str,
    api_key: str,
    count: int,
    opener: Callable[..., Any],
) -> dict[str, Any]:
    body = json.dumps(
        {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "topic": "general",
            "max_results": count,
            "include_answer": False,
            "include_raw_content": False,
        }
    ).encode("utf-8")
    request = Request(
        API_ENDPOINT,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "leadgen-module/1.0",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
            if not isinstance(body, dict):
                raise LeadSearchError("Tavily Search returned an invalid response.")
            return body
    except HTTPError as exc:
        if exc.code in {403, 429}:
            reason = "API quota/access limit reached"
        else:
            reason = f"Search API returned HTTP {exc.code}"
        raise LeadSearchError(f"Tavily {reason}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise LeadSearchError(
            f"Tavily Search request failed ({type(exc).__name__}); "
            "check connectivity and try again later."
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LeadSearchError("Tavily Search returned invalid JSON.") from exc


def _make_lead(item: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, str]:
    title = item.get("title")
    link = item.get("link")
    snippet = item.get("snippet")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Search result is missing its title.")
    if not isinstance(link, str) or not link.strip():
        raise ValueError("Search result is missing its source URL.")
    evidence = snippet.strip() if isinstance(snippet, str) else ""
    if not evidence:
        evidence = title.strip()
    observed = " ".join(evidence.split())[:500]
    why = (
        f"Observed in the search listing: {observed} "
        f"Inference: it may be relevant to {config['target_customer']} and "
        f"{config['business_idea']}; verify before outreach."
    )
    return {
        "name": title.strip(),
        "handle": "",
        "contact": "",
        "why": why,
        "where": link.strip(),
    }


def _discover(
    config: Mapping[str, Any],
    *,
    api_key: str | None = None,
    opener: Callable[..., Any] | None = None,
) -> tuple[list[dict[str, str]], int, int]:
    validated_config = _validate_config(config)
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        raise LeadSearchError(
            "Set TAVILY_API_KEY in the environment before searching."
        )

    query = (
        f"{validated_config['business_idea']} "
        f"{validated_config['target_customer']} "
        f"{validated_config['location']}"
    )
    request_opener = opener or urlopen
    candidates: list[dict[str, str]] = []
    discovered = 0
    rejected = 0
    response = _search_request(
        query, key, validated_config["limit"], request_opener
    )
    items = response.get("results")
    if not isinstance(items, list):
        raise LeadSearchError("Tavily Search returned invalid result items.")
    discovered = len(items)
    for item in items:
        try:
            if not isinstance(item, Mapping):
                raise ValueError("Search result is not an object.")
            normalized_item = {
                "title": item.get("title"),
                "link": item.get("url"),
                "snippet": item.get("content"),
            }
            candidates.append(_make_lead(normalized_item, validated_config))
        except ValueError as exc:
            rejected += 1
            logger.info("Rejected a search result: %s", exc)

    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            lead = validate_lead(candidate)
        except ValueError as exc:
            rejected += 1
            logger.info("Rejected a candidate lead: %s", exc)
            continue
        keys = _dedupe_keys(lead)
        if keys & seen:
            rejected += 1
            continue
        seen.update(keys)
        unique.append(lead)
    if len(unique) > validated_config["limit"]:
        rejected += len(unique) - validated_config["limit"]
    return unique[: validated_config["limit"]], discovered, rejected


def search_leads(config: Mapping[str, Any]) -> list[dict[str, str]]:
    """Search Tavily and return validated, deduplicated leads.

    Requires TAVILY_API_KEY in the process environment.
    Search results are evidence sources, not verification that a lead is qualified.
    """
    leads, _, _ = _discover(config)
    return leads


def save_leads(leads: Iterable[Mapping[str, Any]], path: str | Path) -> None:
    cleaned = deduplicate_leads(leads)
    destination = _resolve_path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temp_path = Path(temporary_file.name)
            json.dump(cleaned, temporary_file, indent=2, ensure_ascii=False)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temp_path, destination)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def export_markdown(leads: Iterable[Mapping[str, Any]], path: str | Path) -> None:
    cleaned = deduplicate_leads(leads)

    def cell(value: str) -> str:
        return value.replace("|", r"\|").replace("\r", " ").replace("\n", " ")

    lines = [
        "# Discovered leads",
        "",
        "| Name | Handle | Contact | Why | Where |",
        "| --- | --- | --- | --- | --- |",
    ]
    for lead in cleaned:
        cells = [cell(lead[field]) for field in ("name", "handle", "contact", "why", "where")]
        lines.append("| " + " | ".join(cells) + " |")
    destination = _resolve_path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_config(path: str | Path) -> dict[str, Any]:
    config_path = _resolve_path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LeadSearchError(f"Invalid JSON in {config_path}: {exc.msg}.") from exc
    except OSError as exc:
        raise LeadSearchError(f"Cannot read config {config_path}: {exc}.") from exc
    return _validate_config(data)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover business prospects with Tavily Search."
    )
    parser.add_argument("--config", default="lead_search.json", help="JSON search config.")
    parser.add_argument("--output", default="leads.json", help="Output leads JSON path.")
    parser.add_argument(
        "--markdown",
        default="leads.md",
        help="Markdown export path (default: leads.md beside this module).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        config = _load_config(args.config)
        leads, discovered, rejected = _discover(config)
        save_leads(leads, args.output)
        export_markdown(leads, args.markdown)
    except (LeadSearchError, OSError, ValueError) as exc:
        parser.error(str(exc))

    print(
        f"Discovered {discovered} search result(s); rejected {rejected}; "
        f"saved {len(leads)} lead(s) to {_resolve_path(args.output)}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
