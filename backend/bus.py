"""Message bus: every agent posts here; the UI subscribes via SSE. History is kept for replay."""
import asyncio, time, uuid
from dataclasses import dataclass, field, asdict

@dataclass
class Message:
    sender: str                 # agent name or "founder"
    text: str
    channel: str = "group"      # "group" or an agent name (DM chat)
    kind: str = "message"       # message | file_update | approval_request | status
    meta: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    ts: float = field(default_factory=time.time)

    def to_dict(self): return asdict(self)

class Bus:
    def __init__(self):
        self.history: list[Message] = []
        self.subs: list[asyncio.Queue] = []

    async def post(self, msg: Message):
        self.history.append(msg)
        for q in self.subs:
            q.put_nowait(msg)
        print(f"[{msg.channel}] {msg.sender}: {msg.text[:90]}")  # handy dev log

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(); self.subs.append(q); return q

    def unsubscribe(self, q): self.subs.remove(q)
