"""Sandboxed Gmail outreach adapter for the reusable sender package."""

import asyncio
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.local", override=False)
project_root_string = str(PROJECT_ROOT)
if project_root_string not in sys.path:
    sys.path.insert(0, project_root_string)

from sender import (  # noqa: E402
    InputValidationError,
    load_suppressions,
    send_batch,
    validate_email_address,
    validate_records,
)

SENDER_DIRECTORY = PROJECT_ROOT / "sender"
RESULTS_FILE = SENDER_DIRECTORY / "results.json"
OPT_OUTS_FILE = SENDER_DIRECTORY / "opt-outs.json"
VARIANTS_FILE = PROJECT_ROOT / "backend" / "workspace" / "variants.json"
LANDING_PAGE_FILE = PROJECT_ROOT / "backend" / "workspace" / "landing.md"


def _landing_page_url_from_workspace() -> str | None:
    try:
        landing_content = LANDING_PAGE_FILE.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError(
            f"Cannot read landing page workspace file: {LANDING_PAGE_FILE}."
        ) from exc

    match = re.search(
        rb"<!--\s*live:\s*(https://[^\s>]+)\s*-->",
        landing_content,
        re.IGNORECASE,
    )
    return match.group(1).decode("ascii") if match else None


def _personalized_variant_from_json(
    lead: dict[str, Any],
    variant_key: str,
    variants_file: str | Path | None = None,
    landing_url: str | None = None,
) -> tuple[str, str]:
    if not isinstance(variant_key, str) or variant_key not in {"A", "B", "C", "D", "E", "F"}:
        raise ValueError("variant must be one of A, B, C, D, E, or F.")
    source = Path(variants_file) if variants_file is not None else VARIANTS_FILE
    try:
        variants = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Marketing variants file is invalid JSON: {source}.") from exc
    except OSError as exc:
        raise RuntimeError(f"Cannot read marketing variants file: {source}.") from exc

    valid_key_sets = ({"A", "B", "C", "D"}, {"A", "B", "C", "D", "E", "F"})
    if not isinstance(variants, dict) or set(variants) not in valid_key_sets:
        raise ValueError("Marketing variants file must contain A-D, optionally with both E and F.")
    if variant_key not in variants:
        raise ValueError(f"Variant {variant_key} is not present in the Marketing variants file.")
    selected = variants[variant_key]
    expected_angles = {
        "A": "pain-point",
        "B": "social-proof",
        "C": "question",
        "D": "offer-first",
        "E": "curiosity-led",
        "F": "proof-led",
    }
    if (
        not isinstance(selected, dict)
        or set(selected) != {"angle", "subject", "text"}
        or selected["angle"] != expected_angles[variant_key]
        or not isinstance(selected["subject"], str)
        or not selected["subject"].strip()
        or "\r" in selected["subject"]
        or "\n" in selected["subject"]
        or len(selected["subject"].split()) > 8
        or not isinstance(selected["text"], str)
        or not selected["text"].strip()
    ):
        raise ValueError(
            f"Variant {variant_key} must contain the expected angle, a subject "
            "of at most 8 words without line breaks, and non-empty text."
        )

    name = lead.get("name")
    if not isinstance(name, str) or not name.strip():
        name = "there"
    offer = lead.get("offer")
    if not isinstance(offer, str) or not offer.strip():
        raise ValueError("Provide the business offer for {offer} personalization.")
    message = selected["text"]
    if "{why}" in message:
        raise ValueError(
            f"Variant {variant_key} still uses the retired {{why}} placeholder. "
            "Regenerate variants.json before sending."
        )
    if "{name}" not in message or "{offer}" not in message:
        raise ValueError(
            f"Variant {variant_key} must include {{name}} and {{offer}}."
        )
    if not isinstance(landing_url, str) or not landing_url.strip():
        raise ValueError(
            "A deployed landing page URL is required to fill the {link} placeholder."
        )
    message = message.replace("{name}", name.strip()).replace(
        "{offer}", " ".join(offer.split())
    )
    if "{link}" in message:
        message = message.replace("{link}", landing_url.strip())
    else:
        message = f"{message.rstrip()}\n\n{landing_url.strip()}"
    return (
        selected["subject"].strip(),
        message,
    )


def _message_from_variant(
    lead: dict[str, Any],
    variant_key: str,
    variants_file: str | Path | None = None,
    landing_url: str | None = None,
) -> str:
    return _personalized_variant_from_json(
        lead, variant_key, variants_file, landing_url
    )[1]


def _send_test_email(
    lead: dict[str, Any],
    text: str,
    *,
    subject: str,
    dry_run: bool,
    compliance_confirmed: bool,
) -> dict[str, Any]:
    candidate = lead.get("email") or lead.get("contact")
    if not isinstance(candidate, str) or not candidate.strip():
        raise InputValidationError(
            "This outreach path requires an email address in the lead's email "
            "or contact field. A public profile handle cannot be used as a "
            "Gmail recipient."
        )
    recipient = validate_email_address(candidate)

    allowed_test_email = os.getenv("OUTREACH_TEST_EMAIL", "").strip()
    if not allowed_test_email:
        raise RuntimeError(
            "Set OUTREACH_TEST_EMAIL in the repository-root .env.local file "
            "to an inbox you control before using the outreach adapter."
        )
    allowed_test_email = validate_email_address(
        allowed_test_email, "OUTREACH_TEST_EMAIL"
    )
    if recipient.casefold() != allowed_test_email.casefold():
        raise PermissionError(
            "Sandbox outreach is restricted to the configured OUTREACH_TEST_EMAIL."
        )

    name = lead.get("name")
    if not isinstance(name, str) or not name.strip():
        name = recipient
    records = validate_records(
        [{"name": name.strip(), "email": recipient, "message": text}]
    )
    if "\r" in subject or "\n" in subject:
        raise ValueError("subject must not contain line breaks.")
    suppressions = load_suppressions(OPT_OUTS_FILE)
    if dry_run:
        if recipient.casefold() in suppressions:
            return {
                "ok": False,
                "id": None,
                "recipient": recipient,
                "status": "skipped",
                "error": "Recipient is present in the opt-out suppression list.",
            }
        return {
            "ok": False,
            "id": None,
            "recipient": recipient,
            "status": "dry_run",
            "error": None,
        }
    if compliance_confirmed is not True:
        raise ValueError(
            "Live outreach requires explicit compliance confirmation."
        )

    result = send_batch(
        records,
        results_path=RESULTS_FILE,
        suppressed_emails=suppressions,
        subject=subject,
        compliance_confirmed=True,
    )[0]
    return {
        **result,
        "ok": result["status"] == "accepted",
        "id": result["provider_message_id"],
    }


async def send_dm(
    lead: dict[str, Any],
    text: str | None = None,
    *,
    variant: str | None = None,
    variants_file: str | Path | None = None,
    landing_url: str | None = None,
    subject: str | None = None,
    dry_run: bool = True,
    compliance_confirmed: bool = False,
) -> dict[str, Any]:
    """Send email to the configured sandbox inbox; dry-run unless opted in.

    The legacy name is retained for the backend interface, but this sends
    email through Gmail and does not send a platform direct message.
    """
    if not isinstance(lead, dict):
        raise TypeError("lead must be a dictionary.")
    if landing_url is None:
        landing_url = _landing_page_url_from_workspace()
    if landing_url is not None:
        if not isinstance(landing_url, str):
            raise TypeError("landing_url must be a string or None.")
        landing_url = landing_url.strip()
        parsed_url = urlsplit(landing_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or any(char.isspace() for char in landing_url)
            or "\r" in landing_url
            or "\n" in landing_url
        ):
            raise ValueError("landing_url must be an absolute HTTPS URL.")
    if variant is not None:
        if text is not None:
            raise ValueError("Provide either text or variant, not both.")
        subject, text = _personalized_variant_from_json(
            lead, variant, variants_file, landing_url
        )
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Provide non-empty text or a variant key from variants.json.")
    if variant is None and landing_url is not None:
        if "{link}" in text:
            text = text.replace("{link}", landing_url)
        else:
            text = f"{text.rstrip()}\n\n{landing_url}"
    if subject is None:
        subject = "A quick introduction"
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("subject must be non-empty.")
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run must be a boolean.")
    if not isinstance(compliance_confirmed, bool):
        raise TypeError("compliance_confirmed must be a boolean.")
    return await asyncio.to_thread(
        _send_test_email,
        lead,
        text,
        subject=subject,
        dry_run=dry_run,
        compliance_confirmed=compliance_confirmed,
    )


async def poll_replies() -> list[dict[str, str]]:
    """Reply polling is not implemented for Gmail; no replies are fabricated."""
    return []
