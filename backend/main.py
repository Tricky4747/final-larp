"""FastAPI surface for the frontend (Person A). Run: uvicorn main:app --reload"""
import asyncio, json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from bus import Bus, Message
from workspace import Workspace
from control import Control
from chat import ChatRouter

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
bus = Bus(); ws = Workspace(bus=bus); ctl = Control(ws, bus, auto_approve=False)

chat = ChatRouter(ctl)


async def _stream_messages(message_bus: Bus):
    # Subscribe before replaying history so events posted during replay remain queued.
    queue = message_bus.subscribe()
    try:
        history = list(message_bus.history)
        for message in history:
            yield {"data": json.dumps(message.to_dict())}
        while True:
            message = await queue.get()
            yield {"data": json.dumps(message.to_dict())}
    finally:
        message_bus.unsubscribe(queue)


@app.post("/idea")
async def idea(body: dict):
    chat.start_pipeline(body["idea"]); return {"ok": True}

@app.post("/round")
async def round_endpoint(body: dict | None = None):
    body = body or {}
    n = max(1, min(int(body.get("n", 10)), 20))
    round_number = ctl.round + 1
    asyncio.create_task(ctl.next_round(n))
    return {"ok": True, "round": round_number, "leads": n}

@app.post("/chat")
async def chat_endpoint(body: dict):
    channel = body.get("channel", "group")
    await bus.post(Message(sender="founder", text=body["text"], channel=channel))
    chat.spawn(chat.handle(body["text"], channel)); return {"ok": True}
    
@app.get("/stream")                      # SSE: every Message as JSON
async def stream():
    return EventSourceResponse(_stream_messages(bus))

@app.get("/agents")                      # sidebar list
def agents(): return [{"name": "Control"}] + [{"name": a.name} for a in ctl.agents.values()]

@app.get("/files")
def files(): return ws.list()

@app.get("/files/{name}")
def file(name: str): return {"name": name, "content": ws.read(name)}

@app.get("/experiments")
def experiments(): return ctl.exp.stats()

@app.post("/approve/{aid}")
async def approve(aid: str, body: dict):
    await ctl.approve(aid, body.get("ok", True), body.get("feedback", "")); return {"ok": True}
