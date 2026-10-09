"""Agents that need real tools. Subclass Agent, override gather() and/or finalize(). Register in CUSTOM.
Key = the key in agents/specs.py SPECS. Control picks these up automatically."""
import json
import re
from agent import Agent
from bus import Message
from tools.search import web_search
from tools.deploy import deploy_html
from tools.leads import find_leads

class ValidationAgent(Agent):               # OWNER: Person C
    async def gather(self, task):
        idea = self.ws.read("idea.md")
        await self.say("Searching competitors...", channel=self.name, kind="status")
        hits = await web_search(f"competitors for: {idea[:150]}")
        hits += await web_search(f"customer complaints reviews: {idea[:150]}")
        return "\n".join(f"- {h['title']} ({h['url']}): {h['snippet']}" for h in hits)

class LandingPageAgent(Agent):              # OWNER: Person C
    async def finalize(self, out):
        html = re.sub(r"^```html|```$", "", out.strip(), flags=re.M).strip()
        idea = self.ws.read("idea.md").replace("# Idea", "").strip()
        slug = re.sub(r"[^a-z0-9]+", "-", idea.lower())[:24].strip("-") or "demo"
        url = await deploy_html(html, slug)
        await self.bus.post(Message(sender=self.name, text=f"Landing page is live: {url}", meta={"url": url}))
        return f"<!-- live: {url} -->\n{html}"

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
    async def gather(self, task):
        leads = await find_leads(query=self.ws.read("plan.md")[:200], location="Chennai", n=10)
        return "\n".join(f"- {l['name']} | {l['handle']} | {l['contact']} | {l['why']}" for l in leads)

CUSTOM = {
    "validation": ValidationAgent,
    "landing": LandingPageAgent,
    "leads": LeadGenAgent,
    "marketing": MarketingAgent,
}
