"""Tests for the marketing variants JSON contract."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agents.custom import MarketingAgent
from agents.specs import SPECS
from bus import Bus
from workspace import Workspace


class MarketingVariantsTests(unittest.IsolatedAsyncioTestCase):
    async def test_marketing_agent_writes_structured_variants_json(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(root=directory, bus=Bus())
            agent = MarketingAgent(SPECS["marketing"], workspace, workspace.bus)
            with patch("agent.complete", new=AsyncMock(return_value=SPECS["marketing"].mock)):
                await agent.run("Write DM variants.")

            saved_path = Path(directory) / "variants.json"
            saved = json.loads(saved_path.read_text(encoding="utf-8"))

        self.assertEqual(set(saved), {"A", "B", "C", "D"})
        self.assertEqual(SPECS["marketing"].writes, "variants.json")
        for variant in saved.values():
            self.assertLess(len(variant["text"].split()), 60)
            self.assertIn("{name}", variant["text"])
            self.assertIn("{why}", variant["text"])

    async def test_marketing_agent_rejects_invalid_json_output(self):
        agent = MarketingAgent(SPECS["marketing"], Workspace(), Bus())
        with self.assertRaisesRegex(ValueError, "valid variants.json"):
            await agent.finalize("A: plain text")

    async def test_marketing_agent_rejects_missing_personalization_placeholders(self):
        agent = MarketingAgent(SPECS["marketing"], Workspace(), Bus())
        output = {
            key: {"angle": value["angle"], "text": "A generic message."}
            for key, value in json.loads(SPECS["marketing"].mock).items()
        }
        with self.assertRaisesRegex(ValueError, "placeholders"):
            await agent.finalize(json.dumps(output))

    async def test_marketing_agent_accepts_challengers_with_expected_json_angles(self):
        agent = MarketingAgent(SPECS["marketing"], Workspace(), Bus())
        variants = json.loads(SPECS["marketing"].mock)
        variants.update({
            "E": {"angle": "curiosity-led", "text": "Hi {name}, {why}. What would you change?"},
            "F": {"angle": "proof-led", "text": "Hi {name}, {why}. May I share an overview?"},
        })

        saved = json.loads(await agent.finalize(json.dumps(variants)))

        self.assertEqual(set(saved), {"A", "B", "C", "D", "E", "F"})


if __name__ == "__main__":
    unittest.main()
