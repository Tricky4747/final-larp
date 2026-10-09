"""FastAPI surface for the frontend (Person A). Run: uvicorn main:app --reload"""
import asyncio, json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from bus import Bus
from workspace import Workspace
from control import Control

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
bus = Bus(); ws = Workspace(bus=bus); ctl = Control(ws, bus)

@app.post("/idea")
async def idea(body: dict):
    asyncio.create_task(ctl.run_pipeline(body["idea"])); return {"ok": True}

@app.get("/stream")                      # SSE: every Message as JSON
async def stream():
    async def gen():
        for m in bus.history: yield {"data": json.dumps(m.to_dict())}   # replay on reconnect
        q = bus.subscribe()
        try:
            while True: yield {"data": json.dumps((await q.get()).to_dict())}
        finally: bus.unsubscribe(q)
    return EventSourceResponse(gen())

@app.get("/files")
def files(): return ws.list()

@app.get("/files/{name}")
def file(name: str): return {"name": name, "content": ws.read(name)}

@app.get("/experiments")
def experiments(): return ctl.exp.stats()

@app.post("/approve/{aid}")
async def approve(aid: str, body: dict):
    await ctl.approve(aid, body.get("ok", True)); return {"ok": True}
