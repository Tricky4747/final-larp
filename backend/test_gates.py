"""Scripted founder: tests approve / request-changes / cancel paths. Run: python test_gates.py"""
import asyncio, os, shutil
from bus import Bus
from workspace import Workspace
from control import Control

def fresh():
    shutil.rmtree("workspace", ignore_errors=True)
    if os.path.exists("experiments.db"): os.remove("experiments.db")

async def run(script):
    """script: {stage: [ (ok, feedback), ... ]} answers consumed in order; default = approve."""
    fresh(); bus = Bus(); ws = Workspace(bus=bus); c = Control(ws, bus, auto_approve=False)
    q = bus.subscribe(); stages = []
    async def founder():
        while True:
            m = await q.get()
            if m.kind == "approval_request":
                st = m.meta["stage"]; stages.append(st)
                ok, fb = script.get(st, []).pop(0) if script.get(st) else (True, "")
                await c.approve(m.meta["id"], ok, fb)
    t = asyncio.create_task(founder())
    await asyncio.wait_for(c.run_pipeline("A mobile dog grooming van"), 30)
    t.cancel(); return bus, ws, stages

async def main():
    # 1. happy path: every gate appears, in order
    bus, ws, stages = await run({})
    assert stages == ["plan", "landing", "variants", "round1"], stages
    print("OK happy path:", stages)

    # 2. request changes on the plan: planner re-runs, feedback saved, gate asked again
    bus, ws, stages = await run({"plan": [(False, "make the design more playful")]})
    plan_writes = [m for m in bus.history if m.kind == "file_update" and m.meta["file"] == "plan.md"]
    assert stages.count("plan") == 2 and len(plan_writes) == 2, (stages, len(plan_writes))
    assert "more playful" in ws.read("feedback.md")
    print("OK request-changes: plan gate asked twice, planner ran twice, feedback.md saved")

    # 3. reject with empty feedback stops the pipeline before building anything
    bus, ws, stages = await run({"plan": [(False, "")]})
    assert stages == ["plan"] and not ws.read("landing.md")
    print("OK cancel: pipeline stopped at plan, nothing built")

    # 4. feedback on a DM batch regenerates variants, then asks again
    bus, ws, stages = await run({"round1": [(False, "shorter, friendlier messages")]})
    assert stages.count("round1") == 2
    print("OK batch feedback: variants revised, batch re-asked")
    fresh()

asyncio.run(main())
