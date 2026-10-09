"""Control agent: the orchestrator. Runs the pipeline, dispatches tasks, gates on approval, loops."""
import asyncio, json, uuid
from agent import Agent
from agents.specs import SPECS
from bus import Bus, Message
from workspace import Workspace
from experiments import Experiments
from llm import complete
from parsing import parse_variants

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
        if not await self.gate("variants", "Approve these DM variants?", "marketing", file="variants.md"):
            return
        await self.run_round(10)

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
        for v in plan:
            self.exp.record(v, replied=await self.simulate_reply(v))  # swap for real replies later
        s = self.exp.stats(); w = self.exp.winner()
        leader = f"Leading variant: {w}." if w else "Not enough data yet to name a winner."
        await self.say(f"Round {self.round} done. {leader} Stats: {s}")
        await self.ws.append("experiments.md", f"- {s}", "Control")
        await self.learn_round(s)
        return True

    async def learn_round(self, stats: dict):
        variants = parse_variants(self.ws.read("variants.md"))
        variant_context = "\n".join(f"{key}: {text}" for key, text in variants.items())
        prompt = ("Analyze this outreach experiment. Compare the variant wording with the "
                  "reply rates and explain the likely reason for the result. Write exactly "
                  "2-3 sentences of durable lessons for the next marketing round.\n\n"
                  f"VARIANTS:\n{variant_context}\n\nSTATS:\n{json.dumps(stats, sort_keys=True)}")
        fallback = self._fallback_lesson(variants, stats)
        try:
            lesson = await complete("You are the learning lead for an outreach experiment.",
                                    prompt, mock=fallback, max_tokens=500)
        except Exception:
            lesson = fallback
        await self.ws.append("lessons.md", lesson.strip(), "Control")
        await self.say(f"Learned from round {self.round}: {lesson.strip()}")

        winner = self.exp.winner()
        if winner:
            candidates = {key: value for key, value in self.exp.active_stats().items()
                          if key != winner and value["sends"]}
            if candidates:
                loser = min(candidates, key=lambda key: (candidates[key]["rate"], -candidates[key]["sends"]))
                self.exp.retire(loser)
                await self.say(f"Retiring variant {loser}; keeping {winner} as the current winner.")

        output = await self.agents["marketing"].run(
            "Use the new lessons to refresh the DM set. Keep A-D, and generate 1-2 new "
            "challenger variants labelled E and F for the explore slice."
        )
        refreshed = parse_variants(output)
        challengers = {key: text for key, text in refreshed.items() if key in "EF"}
        if not challengers:
            current = parse_variants(self.ws.read("variants.md"))
            current.update({"E": "A new curiosity-led challenger for {name}: {why}",
                            "F": "A concise proof-led challenger for {name}: {why}"})
            await self.ws.write("variants.md", "\n".join(f"{key}: {text}" for key, text in current.items()), "Control")
            challengers = {key: current[key] for key in "EF"}
        for variant in challengers:
            self.exp.register(variant)
        await self.say(f"Marketing added challenger variants: {', '.join(sorted(challengers))}.")

    @staticmethod
    def _fallback_lesson(variants: dict[str, str], stats: dict) -> str:
        active = {key: value for key, value in stats.items() if value["sends"]}
        if not active:
            return "The first round does not provide enough reply data to identify a reliable pattern. Keep testing distinct angles before shifting the majority of sends."
        best = max(active, key=lambda key: active[key]["rate"])
        worst = min(active, key=lambda key: active[key]["rate"])
        return (f"Variant {best} currently leads at {active[best]['rate']:.0%}, while "
                f"variant {worst} trails at {active[worst]['rate']:.0%}; the wording differences "
                "should guide the next challenger angles. More sends are needed before treating this as a stable preference.")

    async def simulate_reply(self, variant: str) -> bool:
        import random
        return random.random() < {"A": .05, "B": .10, "C": .20, "D": .08,
                                  "E": .14, "F": .11}[variant]  # hidden "true" rates
