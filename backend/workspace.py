"""Shared md file system. All agents read/write here; every write is announced to the UI."""
from pathlib import Path
from bus import Bus, Message

class Workspace:
    def __init__(self, root="workspace", bus: Bus | None = None):
        self.root = Path(root); self.root.mkdir(exist_ok=True); self.bus = bus

    def read(self, name: str) -> str:
        p = self.root / name
        return p.read_text() if p.exists() else ""

    async def write(self, name: str, content: str, author: str):
        (self.root / name).write_text(content)
        await self._announce(name, author, "wrote")

    async def append(self, name: str, content: str, author: str):
        with open(self.root / name, "a") as f: f.write("\n" + content)
        await self._announce(name, author, "updated")

    def list(self):
        files = [path.name for path in self.root.glob("*.md")]
        variants = self.root / "variants.json"
        if variants.is_file():
            files.append(variants.name)
        return sorted(files)

    async def _announce(self, name, author, verb):
        if self.bus:
            await self.bus.post(Message(sender=author, text=f"{verb} {name}",
                                        kind="file_update", meta={"file": name}))
