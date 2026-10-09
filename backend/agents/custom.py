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
        if not isinstance(variants, dict) or set(variants) != set(expected):
            raise ValueError("variants.json must contain exactly variants A, B, C, and D.")

        for key, angle in expected.items():
            variant = variants[key]
            if (
                not isinstance(variant, dict)
                or set(variant) != {"angle", "text"}
                or variant["angle"] != angle
                or not isinstance(variant["text"], str)
                or not variant["text"].strip()
            ):
                raise ValueError(
                    f"Variant {key} must contain its expected angle and non-empty text."
                )
            words = variant["text"].split()
            if len(words) >= 60:
                raise ValueError(f"Variant {key} must be under 60 words.")
            if "{name}" not in variant["text"] or "{why}" not in variant["text"]:
                raise ValueError(
                    f"Variant {key} must retain the {{name}} and {{why}} placeholders."
                )
            variant["text"] = variant["text"].strip()
        return json.dumps(variants, ensure_ascii=False, indent=2)

class LeadGenAgent(Agent):                  # OWNER: Person D
    def __init__(self, spec, ws, bus):
        super().__init__(spec, ws, bus)
        self._discovered_leads: ContextVar[tuple[dict[str, str], ...]] = ContextVar(
            f"leadgen_results_{id(self)}", default=()
        )

    async def gather(self, task):
        await self.say("Searching public Reddit posts...", channel=self.name, kind="status")
        leads = await find_leads(query=self.ws.read("plan.md")[:200], location="Chennai", n=10)
        self._discovered_leads.set(tuple(leads))
        if not leads:
            return "No matching public Reddit posts were found."
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
                "No matching public posts were found; leads.md contains the empty results table."
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
