"""Agents that need real tools. Subclass Agent, override gather() and/or finalize(). Register in CUSTOM.
Key = the key in agents/specs.py SPECS. Control picks these up automatically."""
import json
import re
from contextvars import ContextVar
from agent import Agent
from bus import Message
import asyncio
from tools.search import web_search, fetch_page
from tools.deploy import deploy_html
from tools.leads import find_leads


_MARKET_FIELD_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?"
    r"(?:target (?:geographic )?market|geographic focus|geography|"
    r"service area|location)\s*:\s*(.+?)\s*$"
)
_MARKET_HEADING_RE = re.compile(
    r"(?im)^\s{0,3}#{1,6}\s*(?:target market|geographic focus|"
    r"geography|service area|location)\s*:?\s*$"
)
_GEOGRAPHIC_CUE_RE = re.compile(
    r"\b(?:in|across|throughout|within|serving|based in|focused on)\s+"
    r"((?:the\s+)?[A-Z][A-Za-z.'’-]*"
    r"(?:(?:\s+(?:of|the|and|&)?\s*|,\s*)[A-Z][A-Za-z.'’-]*){0,4})"
)
_UNSPECIFIED_MARKET_RE = re.compile(
    r"\b(?:not specified|unspecified|not provided|not stated|unknown|anywhere)\b",
    re.IGNORECASE,
)


def _extract_target_market(plan: str, idea: str) -> str | None:
    for document in (plan, idea):
        field = _MARKET_FIELD_RE.search(document)
        if field:
            market = field.group(1).strip(" .")
            if market and not _UNSPECIFIED_MARKET_RE.search(market):
                return market

        for heading in _MARKET_HEADING_RE.finditer(document):
            section = document[heading.end():]
            next_heading = re.search(r"(?m)^\s{0,3}#{1,6}\s+", section)
            if next_heading:
                section = section[:next_heading.start()]
            cue = _GEOGRAPHIC_CUE_RE.search(section)
            if cue and not _UNSPECIFIED_MARKET_RE.search(cue.group(1)):
                return cue.group(1).strip(" .")

    for document in (plan, idea):
        cue = _GEOGRAPHIC_CUE_RE.search(document)
        if cue and not _UNSPECIFIED_MARKET_RE.search(cue.group(1)):
            return cue.group(1).strip(" .")
    return None


class ValidationAgent(Agent):
    async def gather(self, task):
        # Read the founder's business idea.
        idea = self.ws.read("idea.md").strip()

        if not idea:
            return "No business idea was provided in idea.md."

        await self.say(
            "Researching competitors and customer problems...",
            channel=self.name,
            kind="status",
        )

        # Search for competitors and customer complaints in parallel.
        queries = [
            f"competitors and alternatives for: {idea[:150]}",
            f"customer complaints and pain points related to: {idea[:150]}",
        ]

        batches = await asyncio.gather(
            *(web_search(query, n=5) for query in queries)
        )

        # Combine the results and remove duplicate URLs.
        hits = []
        seen_urls = set()

        for batch in batches:
            for result in batch:
                url = result.get("url", "").strip()

                if url and url not in seen_urls:
                    seen_urls.add(url)
                    hits.append(result)

        if not hits:
            return (
                "No search results were returned. "
                "Do not invent competitor research. "
                "Explain that live research could not be completed."
            )

        # Include search-result information in the research context.
        sections = ["## WEB SEARCH RESULTS"]

        for result in hits:
            sections.append(
                f"### {result.get('title', 'Untitled result')}\n"
                f"URL: {result.get('url', '')}\n"
                f"Snippet: {result.get('snippet', '')}"
            )

        # Do not treat the mock example.com result as a real competitor.
        real_hits = [
            result for result in hits
            if not result.get("title", "").startswith("MOCK MODE:")
        ]

        if not real_hits:
            sections.append(
                "\n## PAGE RESEARCH\n"
                "Only mock search results are available. "
                "No real competitor pages were researched."
            )
            return "\n\n".join(sections)

        # Fetch the first three unique result pages.
        pages = await asyncio.gather(
            *(
                fetch_page(result["url"], max_chars=2500)
                for result in real_hits[:3]
            )
        )

        sections.append("\n## FETCHED WEBPAGE CONTENT")

        for result, page_text in zip(real_hits[:3], pages):
            sections.append(
                f"### {result.get('title', 'Untitled page')}\n"
                f"Source: {result.get('url', '')}\n"
                f"{page_text if page_text else 'Page content could not be retrieved.'}"
            )

        return "\n\n".join(sections)




class LandingPageAgent(Agent):
    async def finalize(self, out):
        # Remove Markdown fences if the model accidentally includes them.
        html = re.sub(
            r"^```(?:html)?\s*$",
            "",
            out.strip(),
            flags=re.MULTILINE | re.IGNORECASE,
        ).strip()
        
        lower_html = html.lower()

        required_tags = [
            "<!doctype html",
            "<html",
            "<head",
            "</head>",
            "<body",
            "</body>",
            "</html>",
        ]

        styles_complete = (
            lower_html.count("<style")
            == lower_html.count("</style>")
        )

        if (
            not all(tag in lower_html for tag in required_tags)
            or not styles_complete
        ):
            await self.bus.post(
                Message(
                    sender=self.name,
                    text=(
                        "Landing page HTML is incomplete. "
                        "It was not deployed; regenerate the page."
                    ),
                )
            )
            return f"<!-- live: UNDEPLOYED -->\n{html}"

        # Create a name for the deployed website.
        idea = self.ws.read("idea.md").replace("# Idea", "").strip()
        slug = (
            re.sub(r"[^a-z0-9]+", "-", idea.lower())[:24].strip("-")
            or "demo"
        )

        # Attempt deployment.
        url = await deploy_html(html, slug)

        if url and url.startswith("https://"):
            # Announce success only when a URL is returned.
            await self.bus.post(
                Message(
                    sender=self.name,
                    text=f"Landing page is live: {url}",
                    meta={"url": url},
                )
            )
            return f"<!-- live: {url} -->\n{html}"

        # No live URL: report honestly that deployment did not happen.
        await self.bus.post(
            Message(
                sender=self.name,
                text=(
                    "Landing page HTML was generated, but deployment "
                    "is unavailable. Configure NETLIFY_AUTH_TOKEN "
                    "to publish it."
                ),
            )
        )

        return f"<!-- live: UNDEPLOYED -->\n{html}"


class MarketingAgent(Agent):                # OWNER: Person D
    async def finalize(self, out):
        try:
            variants = json.loads(out)
        except json.JSONDecodeError as exc:
            raise ValueError("Marketing output must be valid variants.json.") from exc

        expected = {
            "A": "pain-point",
            "B": "social-proof",
            "C": "question",
            "D": "offer-first",
        }
        valid_key_sets = (set(expected), set(expected) | {"E", "F"})
        if not isinstance(variants, dict) or set(variants) not in valid_key_sets:
            raise ValueError("variants.json must contain A-D, optionally with both E and F.")
        if "E" in variants:
            expected.update({"E": "curiosity-led", "F": "proof-led"})

        for key, angle in expected.items():
            variant = variants[key]
            if (
                not isinstance(variant, dict)
                or set(variant) != {"angle", "subject", "text"}
                or variant["angle"] != angle
                or not isinstance(variant["subject"], str)
                or not variant["subject"].strip()
                or "\r" in variant["subject"]
                or "\n" in variant["subject"]
                or len(variant["subject"].split()) > 8
                or not isinstance(variant["text"], str)
                or not variant["text"].strip()
            ):
                raise ValueError(
                    f"Variant {key} must contain its expected angle, a subject "
                    "of at most 8 words without line breaks, and non-empty text."
                )
            words = variant["text"].split()
            if len(words) >= 60:
                raise ValueError(f"Variant {key} must be under 60 words.")
            if "{why}" in variant["text"]:
                raise ValueError(
                    f"Variant {key} must not use the {{why}} placeholder."
                )
            if any(
                placeholder not in variant["text"]
                for placeholder in ("{name}", "{offer}", "{link}")
            ):
                raise ValueError(
                    f"Variant {key} must use {{name}}, {{offer}}, and {{link}}."
                )
            variant["text"] = variant["text"].strip()
            variant["subject"] = variant["subject"].strip()
        return json.dumps(variants, ensure_ascii=False, indent=2)

class LeadGenAgent(Agent):                  # OWNER: Person D
    def __init__(self, spec, ws, bus):
        super().__init__(spec, ws, bus)
        self._discovered_leads: ContextVar[tuple[dict[str, str], ...]] = ContextVar(
            f"leadgen_results_{id(self)}", default=()
        )

    async def gather(self, task):
        await self.say(
            "Searching with Tavily for public business websites and published contact emails...",
            channel=self.name,
            kind="status",
        )
        plan = self.ws.read("plan.md").strip()
        idea = self.ws.read("idea.md").strip()
        target_market = _extract_target_market(plan, idea)
        if target_market is None:
            target_market = "Kerala"
            await self.say(
                "No geographic target market was specified in the idea or plan; "
                "defaulting lead searches to Kerala.",
                channel=self.name,
                kind="status",
            )
        leads = await find_leads(
            query=(plan or idea)[:200],
            location=target_market,
            n=25,
        )
        self._discovered_leads.set(tuple(leads))
        if not leads:
            return (
                "Tavily found no matching public business websites with "
                "published contact emails."
            )
        return "\n".join(
            f"- {lead['name']} | {lead['handle']} | {lead['why']}"
            for lead in leads
        )

    async def finalize(self, out):
        headers = ["name", "handle", "contact", "why"]
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        leads = self._discovered_leads.get()
        if not leads:
            await self.say(
                "Tavily found no matching public business websites with "
                "published contact emails; leads.md contains the empty results table."
            )
        for lead in leads:
            values = [
                lead["name"],
                lead["handle"],
                lead["contact"],
                f"{lead['why']} [Source]({lead['source']})",
            ]
            escaped = [
                value.replace("|", r"\|").replace("\r", " ").replace("\n", " ")
                for value in values
            ]
            lines.append("| " + " | ".join(escaped) + " |")
        return "\n".join(lines)

CUSTOM = {
    "validation": ValidationAgent,
    "landing": LandingPageAgent,
    "leads": LeadGenAgent,
    "marketing": MarketingAgent,
}
