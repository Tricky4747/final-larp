"""Test the whole pipeline without the UI: python run_cli.py"""
import asyncio
from bus import Bus
from workspace import Workspace
from control import Control

async def main():
    bus = Bus(); ws = Workspace(bus=bus); c = Control(ws, bus)
    await c.run_pipeline("A mobile dog-grooming van for busy professionals in Chennai")
    await c.run_round(20); await c.run_round(20)   # watch the split shift
    print("\nFILES:", ws.list()); print("STATS:", c.exp.stats())
asyncio.run(main())
