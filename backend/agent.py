"""Declarative agent: a spec + one generic run(). Adding an agent = adding a spec."""
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

    def build_context(self, task: str) -> str:
        parts = [f"## {f}\n{self.ws.read(f)}" for f in self.spec.reads if self.ws.read(f)]
        return "\n\n".join(parts) + f"\n\n## YOUR TASK\n{task}"

    async def run(self, task: str) -> str:
        await self.say(f"On it: {task[:80]}", channel=self.name, kind="status")
        out = await complete(self.spec.system_prompt, self.build_context(task), mock=self.spec.mock)
        if self.spec.writes:
            await self.ws.write(self.spec.writes, out, self.name)
        await self.say(f"Done. Output saved to {self.spec.writes or 'chat'}.")
        return out
