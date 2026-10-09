"""Control agent: the orchestrator. Runs the pipeline, dispatches tasks, gates on approval, loops."""
import asyncio, uuid
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
        if not await self.gate("landing", "Landing page is live. Keep it as is?", "landing", file="landing.md"):
            return
        await self.agents["marketing"].run("Write DM variants.")
        for v in "ABCD": self.exp.register(v)
        if not await self.gate("variants", "Approve these DM variants?", "marketing", file="variants.md"):
            return
        await self.run_round(10)

    async def run_round(self, n: int) -> bool:
        self.round += 1
        plan = self.exp.allocate(n)
        split = ", ".join(f"{v}: {plan.count(v)}" for v in sorted(set(plan)))
        if not await self.gate(f"round{self.round}", f"Round {self.round}: send {n} DMs? Split by variant: {split}",
                               "marketing", file="variants.md"):
            return False
        for v in plan:
            self.exp.record(v, replied=await self.simulate_reply(v))  # swap for real replies later
        s = self.exp.stats(); w = self.exp.winner(min_sends=1)
        await self.say(f"Round {self.round} done. Leading variant: {w}. Stats: {s}")
        await self.ws.append("experiments.md", f"- {s}", "Control")
        await self.ws.append("lessons.md", f"- Variant {w} leads after round {self.round}.", "Control")
        return True

    async def simulate_reply(self, variant: str) -> bool:
        import random
        return random.random() < {"A": .05, "B": .10, "C": .20, "D": .08}[variant]  # hidden "true" rates
