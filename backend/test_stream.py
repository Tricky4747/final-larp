"""Tests for lossless SSE history replay and live delivery."""

import json
import unittest

from bus import Bus, Message
from main import _stream_messages


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_messages_are_queued_while_history_is_replayed(self):
        bus = Bus()
        old_message = Message(sender="Control", text="Existing status")
        await bus.post(old_message)
        events = _stream_messages(bus)

        replayed = await anext(events)
        self.assertEqual(json.loads(replayed["data"])["id"], old_message.id)
        self.assertEqual(len(bus.subs), 1)

        live_message = Message(sender="LandingPage", text="Building the page")
        await bus.post(live_message)
        live = await anext(events)
        self.assertEqual(json.loads(live["data"])["id"], live_message.id)

        await events.aclose()
        self.assertEqual(bus.subs, [])

    async def test_messages_posted_before_connection_are_replayed(self):
        bus = Bus()
        message = Message(sender="Control", text="Idea received")
        await bus.post(message)

        event = await anext(_stream_messages(bus))

        self.assertEqual(json.loads(event["data"])["id"], message.id)
