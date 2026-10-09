"""Founder <-> Control chat. Wraps a Control instance; control.py is NOT modified.

Flow:  POST /chat {text, channel} -> ChatRouter.handle()
  channel = an agent's name  -> DM to that agent (answer / revise only)
  channel = "group"/"Control" -> Control routes: answer | revise | round | setting | restart
Routing uses the LLM when a key is set, and a keyword heuristic in mock mode (so you can test offline).
"""
import asyncio, contextlib, json, os, re
from bus import Message
from llm import complete, parse_json

# when an agent's output changes, these downstream agents may be stale
DOWNSTREAM = {"validation": ["planner"], "planner": ["landing", "leads", "marketing"], "leads": ["marketing"]}

KEYWORDS = {   # heuristic routing (mock mode / fallback only)
    "landing":    ["landing", "page", "website", "headline", "hero", "design", "color", "colour", "button"],
    "planner":    ["plan", "audience", "strategy", "philosophy"],
    "marketing":  ["dm", "message", "copy", "variant", "tone", "pitch", "wording"],
    "leads":      ["lead", "prospect"],
    "validation": ["competitor", "validation", "research", "market", "survey"],
}
REVISE_VERBS = r"\b(make|change|rewrite|redo|update|add|remove|shorter|longer|more|less|fix|replace|use|include|avoid|stop|switch)\b"

ROUTER_PROMPT = """You are the Control agent of a business-building agent team. Decide what to do with the founder's message.
Reply with ONLY JSON, no markdown:
{"action": "answer|revise|round|setting|restart|unclear",
 "agent": "validation|planner|landing|leads|marketing|null",   // for revise: which agent should change its output
 "instruction": "the change request, rephrased clearly",       // for revise
 "epsilon": null, "batch_size": null,                          // for setting: explore share 0-1, DMs per round
 "idea": null}                                                 // for restart: the new business idea
Use "answer" for questions about the work, "round" to send another batch of DMs, "setting" to change explore share or batch size,
"restart" only if the founder clearly wants a brand new idea, "unclear" if you cannot tell."""

HELP = ("I'm not sure what you want. Try: \"make the landing page more playful\", \"why this audience?\", "
        "\"run another round\", \"set explore to 30%\", \"send 5 per round\", or \"new idea: ...\".")

def _clamp(x, lo, hi): return max(lo, min(hi, x))

def heuristic(text: str, dm_key: str | None) -> dict:
    t = text.lower().strip()
    if m := re.search(r"(?:epsilon|explor\w*)\D{0,12}(\d+(?:\.\d+)?)\s*%?", t):
        v = float(m.group(1)); return {"action": "setting", "epsilon": v / 100 if v > 1 else v}
    if m := re.search(r"\b(\d+)\s*(?:dms?\s*)?per round|batch(?: size)?\D{0,6}(\d+)", t):
        return {"action": "setting", "batch_size": int(m.group(1) or m.group(2))}
    if re.search(r"another round|next round|run (?:a )?round|one more round", t):
        return {"action": "round"}
    if re.search(r"\b(restart|start over|new idea)\b", t):
        idea = text.split(":", 1)[1].strip() if ":" in text else re.sub(r"(?i)\b(restart|start over|new idea)\b", "", text).strip()
        return {"action": "restart", "idea": idea}
    if t.endswith("?") or re.match(r"(why|what|how|which|who|when|where|explain|tell me)\b", t):
        return {"action": "answer"}
    if re.search(REVISE_VERBS, t):
        key = dm_key or next((k for k, kws in KEYWORDS.items() if any(w in t for w in kws)), None)
        if key: return {"action": "revise", "agent": key, "instruction": text}
    return {"action": "unclear"}


class ChatRouter:
    def __init__(self, ctl):
        self.ctl, self.ws, self.bus = ctl, ctl.ws, ctl.bus
        self.by_name = {a.name: k for k, a in ctl.agents.items()}     # "LandingPage" -> "landing"
        self.lock = asyncio.Lock()          # serializes agent re-runs triggered from chat
        self.task: asyncio.Task | None = None
        self.batch_size = 10
        self._tasks: set[asyncio.Task] = set()
        # Don't let an approval click resume the pipeline while a chat-triggered revise is running.
        orig = ctl.approve
        async def guarded(aid, ok, feedback=""):
            async with self.lock:
                await orig(aid, ok, feedback)
        ctl.approve = guarded

    # ---------- pipeline lifecycle (main.py's /idea calls start_pipeline) ----------
    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    @property
    def waiting(self) -> bool:
        """True if the pipeline is paused at one of ITS OWN approval gates (a safe moment to re-run agents)."""
        for m in reversed(self.bus.history):
            if m.kind == "approval_request" and m.meta.get("stage") not in ("cascade", "restart"):
                f = self.ctl.approvals.get(m.meta["id"])
                return bool(f and not f.done())
        return False

    def spawn(self, coro):
        t = asyncio.create_task(coro); self._tasks.add(t); t.add_done_callback(self._tasks.discard); return t

    def start_pipeline(self, idea: str):
        def _done(t):
            if not t.cancelled() and t.exception():
                self.spawn(self.ctl.say(f"Pipeline error: {t.exception()}"))
        self.task = asyncio.create_task(self.ctl.run_pipeline(idea)); self.task.add_done_callback(_done)

    # ---------- entry point ----------
    async def reply(self, text, channel="group", sender="Control"):
        await self.bus.post(Message(sender=sender, text=text, channel=channel))

    async def handle(self, text: str, channel: str = "group"):
        dm_key = self.by_name.get(channel)
        sender = channel if dm_key else "Control"
        try:
            d = await self.route(text, dm_key)
            act = d["action"]
            if dm_key and act in ("round", "setting", "restart"):
                return await self.reply("That's a team-wide change. Ask Control in the group chat.", channel, sender)
            if act == "answer":   await self.answer(text, channel, sender)
            elif act == "revise": await self.do_revise(d["agent"], d.get("instruction") or text, channel, sender)
            elif act == "round":  await self.do_round(channel)
            elif act == "setting": await self.do_setting(d, channel)
            elif act == "restart": await self.do_restart(d.get("idea"), channel)
            else: await self.reply(HELP, channel, sender)
        except Exception as e:     # a chat failure must never take the pipeline down
            await self.reply(f"Sorry, that failed: {e}", channel, sender)

    # ---------- routing ----------
    async def route(self, text, dm_key) -> dict:
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            d = heuristic(text, dm_key)
        else:
            ctx = f"Files: {self.ws.list()}\nAgents: {list(self.ctl.agents)}\nDM target: {dm_key}\nMessage: {text}"
            try:
                d = parse_json(await complete(ROUTER_PROMPT, ctx, mock=""))
            except Exception:
                d = {"action": "unclear"}
        if d.get("action") not in ("answer", "revise", "round", "setting", "restart"):
            return {"action": "unclear"}
        if dm_key and d["action"] == "revise":
            d["agent"] = dm_key
        if d["action"] == "revise" and d.get("agent") not in self.ctl.agents:
            return {"action": "unclear"}
        return d

    # ---------- actions ----------
    async def answer(self, text, channel, sender):
        ctx = "\n\n".join(f"## {f}\n{self.ws.read(f)[:3000]}" for f in self.ws.list() if self.ws.read(f))
        out = await complete(
            f"You are {sender}, part of a business-building agent team. Answer the founder's question using ONLY the project files. "
            "Be concise. If the files don't contain the answer, say so.",
            f"{ctx}\n\nQUESTION: {text}",
            mock=f"(mock answer) I'd answer from: {', '.join(self.ws.list()) or 'no files yet'}.")
        await self.reply(out, channel, sender)

    async def _wait_safe(self, channel, sender):
        if self.running and not self.waiting:
            await self.reply("I'm mid-step. I'll apply this as soon as it finishes.", channel, sender)
            while self.running and not self.waiting:
                await asyncio.sleep(0.2)

    async def do_revise(self, key, instruction, channel, sender):
        agent = self.ctl.agents[key]; out_file = agent.spec.writes
        if not (out_file and self.ws.read(out_file)):
            await self.ws.append("feedback.md", f"- [{agent.name}] {instruction}", "founder")
            return await self.reply(f"{agent.name} hasn't produced anything yet. I saved your note and it will apply when it runs.", channel, sender)
        await self._wait_safe(channel, sender)
        async with self.lock:
            await self.ctl.revise(key, instruction)
        await self.reply(f"{agent.name} updated {out_file}.", channel, sender)
        await self.cascade(key)

    async def cascade(self, key):
        todo = [k for k in DOWNSTREAM.get(key, []) if self.ctl.agents[k].spec.writes and self.ws.read(self.ctl.agents[k].spec.writes)]
        if not todo: return
        names = ", ".join(self.ctl.agents[k].name for k in todo)
        r = await self.ctl.ask_founder(f"{self.ctl.agents[key].name}'s output changed. Regenerate {names} to match?", stage="cascade")
        if not r["ok"]: return
        for k in todo:      # sequential: marketing reads leads
            async with self.lock:
                await self.ctl.agents[k].run("Regenerate your output so it matches the updated upstream files.")

    async def do_round(self, channel):
        if self.running:
            return await self.reply("The pipeline is still running. Ask again once it finishes.", channel)
        if not self.ctl.exp.stats():
            return await self.reply("There are no DM variants yet. Run the pipeline first.", channel)
        await self.ctl.run_round(_clamp(self.batch_size, 1, 20))        # run_round has its own approval gate

    async def do_setting(self, d, channel):
        parts = []
        if d.get("epsilon") is not None:
            e = _clamp(float(d["epsilon"]), 0.05, 0.5); self.ctl.exp.epsilon = e
            parts.append(f"Explore share set to {e:.0%} (allowed range 5-50%).")
        if d.get("batch_size"):
            self.batch_size = _clamp(int(d["batch_size"]), 1, 20)
            parts.append(f"Batch size set to {self.batch_size} DMs for rounds started from chat (allowed range 1-20).")
        await self.reply(" ".join(parts) or HELP, channel)

    async def do_restart(self, idea, channel):
        idea = (idea or "").strip()
        if len(idea) < 5:
            return await self.reply('What is the new idea? Say "new idea: ..."', channel)
        r = await self.ctl.ask_founder(f'Restart with this new idea? This wipes the current files and experiment stats.\n"{idea}"', stage="restart")
        if not r["ok"]:
            return await self.reply("Okay, keeping the current project.", channel)
        if self.running:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task
        async with self.lock:
            for p in self.ws.root.glob("*.md"): p.unlink()
            self.ctl.exp.db.execute("DELETE FROM v"); self.ctl.exp.db.commit()
            self.ctl.round = 0; self.ctl.approvals.clear()
        self.start_pipeline(idea)
