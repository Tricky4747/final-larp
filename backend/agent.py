"""Declarative agent: a spec + one generic run(). Adding an agent = adding a spec."""
import asyncio
from dataclasses import dataclass, field
from llm import complete
from bus import Bus, Message
from workspace import Workspace

@dataclass
class AgentSpec:
    name: str
    system_prompt: str
    reads: list[str] = field(default_factory=list)    # md files injected as context
    writes: str | None = None                          # md file this agent owns
    mock: str = "(mock output)"

class Agent:
    def __init__(self, spec: AgentSpec, ws: Workspace, bus: Bus):
        self.spec, self.ws, self.bus = spec, ws, bus

    @property
    def name(self): return self.spec.name

    async def say(self, text, channel="group", **kw):
        await self.bus.post(Message(sender=self.name, text=text, channel=channel, **kw))

    def build_context(self, task: str, extra: str = "") -> str:
        parts = [f"## {f}\n{self.ws.read(f)}" for f in self.spec.reads if self.ws.read(f)]
        if extra:
            parts.append(f"## TOOL RESULTS\n{extra}")
        return "\n\n".join(parts) + f"\n\n## YOUR TASK\n{task}"

    # ---- HOOKS: subclasses (agents/custom.py) override these; everything else stays generic ----
    async def gather(self, task: str) -> str:
        """Run tools (search, scrape...) BEFORE the LLM call. Return text to inject as context."""
        return ""

    async def finalize(self, out: str) -> str:
        """Post-process the LLM output (e.g. deploy the HTML). Return the text to save to the md file."""
        return out

    async def run(self, task: str) -> str:
        try:
            return await asyncio.wait_for(self._run(task), timeout=90)
        except Exception as exc:
            reason = str(exc) or type(exc).__name__
            await self.say(f"{self.name} failed: {reason}. Using fallback.", kind="status")
            if self.spec.writes:
                await self.ws.write(self.spec.writes, self.spec.mock, self.name)
            return self.spec.mock

    async def _run(self, task: str) -> str:
        await self.say(f"On it: {task[:80]}", channel=self.name, kind="status")
        extra = await self.gather(task)
        out = await complete(self.spec.system_prompt, self.build_context(task, extra), mock=self.spec.mock)
        out = await self.finalize(out)
        if self.spec.writes:
            await self.ws.write(self.spec.writes, out, self.name)
        await self.say(f"Done. Output saved to {self.spec.writes or 'chat'}.")
        return out
