"""Agents that need real tools. Subclass Agent, override gather() and/or finalize(). Register in CUSTOM.
Key = the key in agents/specs.py SPECS. Control picks these up automatically."""
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
        await self.bus.post(Message(sender=self.name, text=f"Landing page is live: {url}", channel=self.name, meta={"url": url}))
        return f"<!-- live: {url} -->\n{html}"

class LeadGenAgent(Agent):                  # OWNER: Person D
    async def gather(self, task):
        leads = await find_leads(query=self.ws.read("plan.md")[:200], location="Chennai", n=10)
        return "\n".join(f"- {l['name']} | {l['handle']} | {l['contact']} | {l['why']}" for l in leads)

CUSTOM = {"validation": ValidationAgent, "landing": LandingPageAgent, "leads": LeadGenAgent}
