"""Parsers for the markdown contracts shared between agents."""
import re


def parse_variants(md: str) -> dict[str, str]:
    """Parse labelled A-F variants, tolerating markdown bolding and numbering."""
    pattern = re.compile(
        r"^\s*(?:[-*]\s*)?(?:\d+[.)]\s*)?\**([A-F])\**\s*[:.)-]\s*\**\s*(.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    return {match.group(1).upper(): match.group(2).strip() for match in pattern.finditer(md)}
