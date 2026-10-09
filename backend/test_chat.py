"""Scripted founder tests for chat.py (mock mode). Run: python test_chat.py"""
import asyncio, os, shutil
from bus import Bus
from workspace import Workspace
from control import Control
from chat import ChatRouter, heuristic

def fresh():
    shutil.rmtree("workspace", ignore_errors=True)
    if os.path.exists("experiments.db"): os.remove("experiments.db")

async def until(cond, timeout=20):
    t = 0
    while not cond():
        await asyncio.sleep(0.05); t += 0.05
        assert t < timeout, "timed out"

def setup(delays=None):
    fresh(); bus = Bus(); ws = Workspace(bus=bus); c = Control(ws, bus, auto_approve=False); r = ChatRouter(c)
    q = bus.subscribe(); seen = []; delays = delays or {}
    async def founder():                       # approves every card after a delay
        while True:
            m = await q.get()
            if m.kind == "approval_request":
                seen.append(m.meta["stage"]); await asyncio.sleep(delays.get(m.meta["stage"], 0.05))
                await c.approve(m.meta["id"], True)
    return bus, ws, c, r, seen, asyncio.create_task(founder())

writes = lambda bus, f: sum(1 for m in bus.history if m.kind == "file_update" and m.meta["file"] == f)
said = lambda bus, s, ch=None: any(s in m.text and (ch is None or m.channel == ch) and m.sender != "founder" for m in bus.history)
sends = lambda c: sum(v["sends"] for v in c.exp.stats().values())

async def main():
    # --- heuristic router unit checks
    assert heuristic("why this audience?", None)["action"] == "answer"
    assert heuristic("make the landing page more playful", None) == {"action": "revise", "agent": "landing", "instruction": "make the landing page more playful"}
    assert heuristic("set explore to 30%", None)["epsilon"] == 0.3
    assert heuristic("send 5 per round", None)["batch_size"] == 5
    assert heuristic("run another round", None)["action"] == "round"
    assert heuristic("new idea: vegan taco truck", None)["idea"] == "vegan taco truck"
    assert heuristic("blah", None)["action"] == "unclear"
    print("OK heuristic router")

    # --- idle after pipeline
    bus, ws, c, r, seen, ft = setup()
    r.start_pipeline("A mobile dog grooming van"); await r.task
    assert not r.running

    await r.handle("why did you pick this audience?")
    assert said(bus, "(mock answer)", "group"); print("OK question answered in group")

    await r.handle("make the landing page more playful")
    assert writes(bus, "landing.md") == 2 and "playful" in ws.read("feedback.md") and said(bus, "LandingPage updated")
    print("OK revise landing (no cascade needed)")

    await r.handle("make the plan more technical")
    assert "cascade" in seen and writes(bus, "plan.md") == 2
    assert writes(bus, "landing.md") == 3 and writes(bus, "leads.md") == 2 and writes(bus, "variants.json") == 3
    print("OK revise plan -> cascade approved -> landing/leads/marketing regenerated")

    await r.handle("set explore to 30%"); assert c.exp.epsilon == 0.3
    await r.handle("explore 90%"); assert c.exp.epsilon == 0.5          # capped
    await r.handle("send 5 per round"); assert r.batch_size == 5
    await r.handle("send 500 per round"); assert r.batch_size == 20     # capped
    print("OK settings (with caps)")

    r.batch_size = 5; before = sends(c)
    await r.handle("run another round"); assert "round2" in seen and sends(c) == before + 5
    print("OK extra round from chat (approval gate asked, 5 sends)")

    await r.handle("make the messages shorter", channel="Marketing")
    assert writes(bus, "variants.json") == 5 and said(bus, "Marketing updated", "Marketing")
    await r.handle("run another round", channel="Marketing"); assert said(bus, "team-wide", "Marketing")
    print("OK DM to an agent (revise works, team-wide commands redirected)")

    await r.handle("blah"); assert said(bus, "I'm not sure what you want")
    print("OK unclear -> help text")

    await r.handle("new idea: A pop-up vegan taco truck")
    await until(lambda: r.task is not None and r.task.done() and "restart" in seen)
    assert "taco" in ws.read("idea.md") and sends(c) == 10 and c.round == 1
    print("OK restart: approval asked, files + stats wiped, pipeline re-ran on new idea")
    ft.cancel()

    # --- busy: chat arrives mid-step, must wait for the next gate
    bus, ws, c, r, seen, ft = setup({"variants": 1.0})
    orig = c.agents["marketing"].run
    async def slow(task): await asyncio.sleep(1.5); return await orig(task)
    c.agents["marketing"].run = slow
    r.start_pipeline("A mobile dog grooming van")
    await until(lambda: "landing" in seen); await asyncio.sleep(0.3)      # landing approved, marketing now running (slow)
    assert r.running and not r.waiting
    chat_task = r.spawn(r.handle("make the landing page shorter"))
    await until(lambda: said(bus, "mid-step"))
    assert writes(bus, "landing.md") == 1                                   # not applied yet
    await chat_task; await r.task
    assert writes(bus, "landing.md") == 2 and "shorter" in ws.read("feedback.md")
    print("OK busy: chat queued until the next approval gate, then applied")

    # --- agent hasn't run yet: note is saved for later
    bus, ws, c, r, seen, ft = setup({"plan": 0.8})
    r.start_pipeline("A mobile dog grooming van")
    await until(lambda: "plan" in seen)
    await r.handle("make the landing page darker")
    assert "darker" in ws.read("feedback.md") and said(bus, "hasn't produced anything yet")
    await r.task; assert writes(bus, "landing.md") == 1
    print("OK early feedback saved for an agent that hasn't run yet")
    ft.cancel(); fresh()

asyncio.run(main())
