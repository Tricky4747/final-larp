"""Control agent: the orchestrator. Runs the pipeline, dispatches tasks, gates on approval, loops."""
import asyncio, uuid
from agent import Agent
from agents.specs import SPECS
from bus import Bus, Message
from workspace import Workspace
from experiments import Experiments

class Control:
    def __init__(self, ws: Workspace, bus: Bus):
        self.ws, self.bus = ws, bus
        self.agents = {k: Agent(s, ws, bus) for k, s in SPECS.items()}
        self.exp = Experiments()
        self.approvals: dict[str, asyncio.Future] = {}

    async def say(self, text, **kw):
        await self.bus.post(Message(sender="Control", text=text, **kw))

    async def approve(self, approval_id: str, ok: bool):
        if f := self.approvals.get(approval_id): f.set_result(ok)

    async def ask_founder(self, question: str, auto=True) -> bool:
        aid = uuid.uuid4().hex[:6]
        fut = self.approvals[aid] = asyncio.get_running_loop().create_future()
        await self.bus.post(Message(sender="Control", text=question, kind="approval_request", meta={"id": aid}))
        if auto: fut.set_result(True)   # demo/CLI mode; UI mode waits for POST /approve
        return await fut

    async def run_pipeline(self, idea: str):
        await self.ws.write("idea.md", f"# Idea\n{idea}", "founder")
        await self.say("Idea received. Starting validation.")
        await self.agents["validation"].run("Validate this idea.")
        await self.agents["planner"].run("Create the plan.")

        await self.say("Plan ready. Dispatching landing page + lead gen in parallel.")
        await asyncio.gather(
            self.agents["landing"].run("Build the landing page."),
            self.agents["leads"].run("Find target leads."),
        )
        await self.agents["marketing"].run("Write DM variants.")
        for v in "ABCD": self.exp.register(v)

        if not await self.ask_founder("Send first round of DMs to 10 leads?"): return
        await self.run_round(10)

    async def run_round(self, n: int):
        plan = self.exp.allocate(n)
        for v in plan:
            self.exp.record(v, replied=await self.simulate_reply(v))  # swap for real replies later
        s = self.exp.stats(); w = self.exp.winner(min_sends=1)
        await self.say(f"Round done. Leading variant: {w}. Stats: {s}")
        await self.ws.append("experiments.md", f"- {s}", "Control")
        await self.ws.append("lessons.md", f"- Variant {w} leads after this round.", "Control")

    async def simulate_reply(self, variant: str) -> bool:
        import random
        return random.random() < {"A": .05, "B": .10, "C": .20, "D": .08}[variant]  # hidden "true" rates
