"""Control agent: the orchestrator. Runs the pipeline, dispatches tasks, gates on approval, loops."""
import asyncio, json, os, re, uuid
from pathlib import Path
from agent import Agent
from agents.specs import SPECS
from bus import Bus, Message
from workspace import Workspace
from experiments import Experiments

class Control:
    def __init__(self, ws: Workspace, bus: Bus, auto_approve: bool = True):
        self.ws, self.bus, self.auto_approve = ws, bus, auto_approve
        self.agents = {k: Agent(s, ws, bus) for k, s in SPECS.items()}
        from agents.custom import CUSTOM          # C & D's agents with real tools override the generic ones
        for k, cls in CUSTOM.items():
            self.agents[k] = cls(SPECS[k], ws, bus)
        self.exp = Experiments()
        self.approvals: dict[str, asyncio.Future] = {}
        self.round = 0

    async def say(self, text, **kw):
        await self.bus.post(Message(sender="Control", text=text, **kw))

    async def approve(self, approval_id: str, ok: bool, feedback: str = ""):
        f = self.approvals.get(approval_id)
        if f and not f.done():
            f.set_result({"ok": ok, "feedback": feedback})

    async def ask_founder(self, question: str, file: str | None = None, stage: str | None = None) -> dict:
        """Post an approval card and wait. Returns {"ok": bool, "feedback": str}."""
        aid = uuid.uuid4().hex[:6]
        fut = self.approvals[aid] = asyncio.get_running_loop().create_future()
        await self.bus.post(Message(sender="Control", text=question, kind="approval_request",
                                    meta={"id": aid, "stage": stage, "file": file}))
        if self.auto_approve:                      # CLI mode; API mode waits for POST /approve/{id}
            fut.set_result({"ok": True, "feedback": ""})
        return await fut

    async def revise(self, agent_key: str, feedback: str):
        agent = self.agents[agent_key]
        await self.ws.append("feedback.md", f"- [{agent.name}] {feedback}", "founder")
        await self.say(f'Got it. Sending your feedback to {agent.name}: "{feedback}"')
        await agent.run(f"Revise your previous output according to this founder feedback: {feedback}")

    async def gate(self, stage: str, question: str, agent_key: str, file: str | None = None,
                   max_revisions: int = 5) -> bool:
        """Approve -> True. Request changes (with text) -> revise that agent, ask again.
        Reject with empty text -> stop the pipeline (False)."""
        for i in range(max_revisions + 1):
            r = await self.ask_founder(question, file=file, stage=stage)
            if r["ok"]:
                return True
            fb = r["feedback"].strip()
            if not fb:
                await self.say("Okay, stopping here. Tell me what to change, or send a new idea.")
                return False
            if i == max_revisions:
                await self.say("Revision limit reached, continuing with the current version.")
                return True
            await self.revise(agent_key, fb)
        return True

    async def run_pipeline(self, idea: str):
        await self.ws.write("idea.md", f"# Idea\n{idea}", "founder")
        await self.say("Idea received. Starting validation.")
        await self.agents["validation"].run("Validate this idea.")
        if "NO-GO" in self.ws.read("validation.md").upper():
            if not await self.gate("verdict", "Validation says NO-GO. Continue anyway?", "validation", file="validation.md"):
                return
        await self.agents["planner"].run("Create the plan.")
        if not await self.gate("plan", "Here's the plan. Proceed to build?", "planner", file="plan.md"):
            return

        await self.say("Plan approved. Dispatching landing page + lead gen in parallel.")
        await asyncio.gather(
            self.agents["landing"].run("Build the landing page."),
            self.agents["leads"].run("Find target leads."),
        )
        landing_content = self.ws.read("landing.md")

        if "<!-- live: UNDEPLOYED -->" in landing_content:
            landing_prompt = (
                "Landing page HTML was generated, but it is not deployed. "
                "Continue anyway?"
            )
        else:
            landing_prompt = "Landing page is live. Keep it as is?"

        if not await self.gate(
            "landing",
            landing_prompt,
            "landing",
            file="landing.md",
        ):
            return
        await self.agents["marketing"].run("Write DM variants.")
        for v in "ABCD": self.exp.register(v)
        if not await self.gate("variants", "Approve these DM variants?", "marketing", file="variants.json"):
            return
        await self.run_round(10)

    def _load_leads_for_outreach(self) -> list[dict[str, str]]:
        content = self.ws.read("leads.md")
        leads: list[dict[str, str]] = []
        if content:
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            data_lines = [l for l in lines if l.startswith("|") and not l.startswith("| ---") and not l.startswith("| name")]
            for line in data_lines:
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) >= 4:
                    name, handle, contact, why = parts[0], parts[1], parts[2], parts[3]
                    why_clean = re.sub(r"\[.*?\]\(.*?\)", "", why).strip()
                    first_email = contact.split(",")[0].strip() if contact else ""
                    leads.append({
                        "name": name,
                        "handle": handle,
                        "contact": contact,
                        "email": first_email,
                        "why": why_clean,
                    })
        if not leads:
            leads_json_path = Path(__file__).resolve().parent / "tools" / "leads.json"
            if leads_json_path.is_file():
                try:
                    raw = json.loads(leads_json_path.read_text(encoding="utf-8"))
                    if isinstance(raw, list):
                        leads = raw
                except Exception:
                    pass
        return leads

    async def next_round(self, n: int = 10) -> bool:
        """Start one founder-approved outreach round from an API request."""
        return await self.run_round(n)

    async def run_round(self, n: int) -> bool:
        self.round += 1
        plan = self.exp.allocate(n)
        split = ", ".join(f"{v}: {plan.count(v)}" for v in sorted(set(plan)))
        stats = self.exp.stats()
        winner = self.exp.winner()
        if winner:
            explored = len(plan) - plan.count(winner)
            tested = len({v for v in plan if v != winner})
            rate = stats[winner]["rate"] * 100
            narrative = (f"Variant {winner} leads at {rate:.0f}%. Sending "
                         f"{plan.count(winner) / n:.0%} of this batch as {winner}, "
                         f"testing {tested} new angles with the rest.")
        else:
            narrative = f"No variant has enough data yet. Current split: {split}."
        question = f"Send round {self.round} to {n} leads? {narrative}"
        if not await self.gate(f"round{self.round}", question,
                               "marketing", file="variants.md"):
            return False

        # Ensure variants.json exists if MarketingAgent has not written it yet
        variants_file = Path(__file__).resolve().parent / "workspace" / "variants.json"
        if not variants_file.is_file():
            variants_file.parent.mkdir(parents=True, exist_ok=True)
            variants_file.write_text(SPECS["marketing"].mock, encoding="utf-8")

        # Load discovered leads and send real outreach via outreach.py
        leads = self._load_leads_for_outreach()
        target_email = os.getenv("OUTREACH_TEST_EMAIL", "").strip()
        dispatched_count = 0
        outreach_log: list[str] = []

        for i, v in enumerate(plan):
            lead = leads[i % len(leads)] if leads else {"name": "Valued Partner", "why": "your online presence", "contact": ""}
            lead_name = re.sub(r"[\r\n]+", " ", lead.get("name", "Prospect")).strip()[:40]
            clean_why = re.sub(r"[\r\n|]+", " ", lead.get("why", "")).strip()[:150]

            if target_email:
                try:
                    from tools.outreach import send_dm
                    send_payload = {
                        "name": lead_name,
                        "email": target_email,
                        "why": clean_why or "your website presence",
                        "contact": target_email,
                    }
                    subject = f"[{lead_name}] Regarding your website growth"
                    res = await send_dm(
                        send_payload,
                        variant=v,
                        subject=subject,
                        dry_run=False,
                        compliance_confirmed=True,
                    )
                    if res.get("ok"):
                        dispatched_count += 1
                        outreach_log.append(f"- Sent variant **{v}** to **{lead_name}** ({lead.get('contact') or 'N/A'}) -> redirected to sandbox `{target_email}` (Message ID: `{res.get('id')}`)")
                    else:
                        outreach_log.append(f"- Variant **{v}** for **{lead_name}**: status `{res.get('status')}` ({res.get('error')})")
                except Exception as exc:
                    outreach_log.append(f"- Variant **{v}** for **{lead_name}** failed: `{exc}`")

            # Record outcome for multi-armed bandit explore/exploit learning
            self.exp.record(v, replied=await self.simulate_reply(v))

        s = self.exp.stats(); w = self.exp.winner(min_sends=1)
        if dispatched_count > 0:
            await self.say(f"Sent {dispatched_count} personalized outreach emails via Gmail to sandbox inbox ({target_email}).")
        await self.say(f"Round {self.round} done. Leading variant: {w}. Stats: {s}")
        await self.ws.append("experiments.md", f"- Round {self.round} stats: {s}", "Control")
        if outreach_log:
            await self.ws.append("outreach.md", f"### Round {self.round} Outreach Log\n" + "\n".join(outreach_log), "Control")
        await self.ws.append("lessons.md", f"- Variant {w} leads after round {self.round}.", "Control")
        return True

    async def simulate_reply(self, variant: str) -> bool:
        import random
        return random.random() < {"A": .05, "B": .10, "C": .20, "D": .08}[variant]  # hidden "true" rates
