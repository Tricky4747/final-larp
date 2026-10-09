"""Public functions for permitted, search-API-based lead discovery."""

from .lead_scraper import (
    LeadSearchError,
    deduplicate_leads,
    export_markdown,
    save_leads,
    search_leads,
    validate_lead,
)

__all__ = [
    "LeadSearchError",
    "deduplicate_leads",
    "export_markdown",
    "save_leads",
    "search_leads",
    "validate_lead",
]
