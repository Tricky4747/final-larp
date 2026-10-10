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
            self.assertTrue(variant["subject"].strip())
            self.assertLessEqual(len(variant["subject"].split()), 8)
            self.assertNotRegex(variant["subject"], r"[\r\n]")
            self.assertLess(len(variant["text"].split()), 60)
            self.assertIn("{name}", variant["text"])
            self.assertIn("{offer}", variant["text"])
            self.assertIn("{link}", variant["text"])
            self.assertNotIn("{why}", variant["text"])
            self.assertIn("Hi {name},\n\n", variant["text"])

    async def test_marketing_agent_rejects_invalid_json_output(self):
        agent = MarketingAgent(SPECS["marketing"], Workspace(), Bus())
        with self.assertRaisesRegex(ValueError, "valid variants.json"):
            await agent.finalize("A: plain text")

    async def test_marketing_agent_rejects_missing_personalization_placeholders(self):
        agent = MarketingAgent(SPECS["marketing"], Workspace(), Bus())
        output = {
            key: {
                "angle": value["angle"],
                "subject": value["subject"],
                "text": "A generic message with no placeholders.",
            }
            for key, value in json.loads(SPECS["marketing"].mock).items()
        }
        with self.assertRaisesRegex(ValueError, r"\{name\}, \{offer\}, and \{link\}"):
            await agent.finalize(json.dumps(output))

    async def test_marketing_agent_rejects_why_placeholder(self):
        agent = MarketingAgent(SPECS["marketing"], Workspace(), Bus())
        variants = json.loads(SPECS["marketing"].mock)
        variants["A"]["text"] = "Hi {name}, {why} {offer} {link}"

        with self.assertRaisesRegex(ValueError, r"\{why\} placeholder"):
            await agent.finalize(json.dumps(variants))

    async def test_marketing_agent_rejects_subject_with_line_break(self):
        agent = MarketingAgent(SPECS["marketing"], Workspace(), Bus())
        variants = json.loads(SPECS["marketing"].mock)
        variants["A"]["subject"] = "A subject\nwith injected header"

        with self.assertRaisesRegex(ValueError, "subject"):
            await agent.finalize(json.dumps(variants))

    async def test_marketing_agent_accepts_challengers_with_expected_json_angles(self):
        agent = MarketingAgent(SPECS["marketing"], Workspace(), Bus())
        variants = json.loads(SPECS["marketing"].mock)
        variants.update({
            "E": {
                "angle": "curiosity-led",
                "subject": "A question for you",
                "text": "Hi {name},\n\nI am exploring {offer}. What would you change?\n\n{link}",
            },
            "F": {
                "angle": "proof-led",
                "subject": "A practical idea to share",
                "text": "Hi {name},\n\nMay I share an overview of {offer}?\n\n{link}",
            },
        })

        saved = json.loads(await agent.finalize(json.dumps(variants)))

        self.assertEqual(set(saved), {"A", "B", "C", "D", "E", "F"})


if __name__ == "__main__":
    unittest.main()
