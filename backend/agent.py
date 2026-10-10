"""Declarative agent: a spec + one generic run(). Adding an agent = adding a spec."""
import asyncio
from dataclasses import dataclass, field
from llm import complete
from bus import Bus, Message
from memory import search
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
        parts = []
        retrieved_files = {}
        for file in self.spec.reads:
            content = self.ws.read(file)
            if not content:
                continue
            if file in ("lessons.md", "validation.md") and len(content) > 2000:
                hits = search(task, k=3, file=file)
                if hits:
                    retrieved_files[file] = len(hits)
                    content = "\n\n".join(hit["text"] for hit in hits)
            parts.append(f"## {file}\n{content}")
        if retrieved_files:
            retrieved = sum(retrieved_files.values())
            if len(retrieved_files) == 1:
                file = next(iter(retrieved_files))
                source = "lessons" if file == "lessons.md" else "validation reports"
                notice = f"{self.name} retrieved {retrieved} {source} from memory."
            else:
                notice = f"{self.name} retrieved {retrieved} context chunks from memory."
            asyncio.create_task(self.say(
                notice,
                kind="status",
            ))
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
        max_tokens = 12000 if self.spec.writes == "landing.md" else 4000

        out = await complete(
            self.spec.system_prompt,
            self.build_context(task, extra),
            mock=self.spec.mock,
            max_tokens=max_tokens,
        )
        out = await self.finalize(out)
        if self.spec.writes:
            await self.ws.write(self.spec.writes, out, self.name)
        await self.say(f"Done. Output saved to {self.spec.writes or 'chat'}.")
        return out
