"""Tests for publishing lead discovery into the shared workspace."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agents.custom import LeadGenAgent
from agents.specs import SPECS
from bus import Bus
from workspace import Workspace


class LeadAgentWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_writes_discovered_rows_to_shared_leads_markdown(self):
        lead = {
            "name": "Skills question?",
            "handle": "u/public_user",
            "contact": "",
            "source": "https://www.reddit.com/r/careerguidance/comments/post/",
            "why": "Public post asks for career guidance.",
        }
        with tempfile.TemporaryDirectory() as directory:
            bus = Bus()
            workspace = Workspace(root=directory, bus=bus)
            await workspace.write("plan.md", "Career coaching for professionals.", "founder")
            agent = LeadGenAgent(SPECS["leads"], workspace, bus)
            with patch("agents.custom.find_leads", new=AsyncMock(return_value=[lead])), patch(
                "agent.complete", new=AsyncMock(return_value="hallucinated LLM row")
            ):
                await agent.run("Find target leads.")

            shared_content = (Path(directory) / "leads.md").read_text(encoding="utf-8")
            updates = [
                message
                for message in bus.history
                if message.kind == "file_update" and message.meta.get("file") == "leads.md"
            ]

        self.assertTrue(shared_content.startswith("| name | handle | contact | why |"))
        self.assertIn("u/public_user", shared_content)
        self.assertIn("[Source](https://www.reddit.com/r/careerguidance/comments/post/)", shared_content)
        self.assertNotIn("hallucinated LLM row", shared_content)
        self.assertEqual(len(updates), 1)

    async def test_empty_discovery_publishes_empty_table_and_group_message(self):
        with tempfile.TemporaryDirectory() as directory:
            bus = Bus()
            workspace = Workspace(root=directory, bus=bus)
            agent = LeadGenAgent(SPECS["leads"], workspace, bus)
            with patch("agents.custom.find_leads", new=AsyncMock(return_value=[])), patch(
                "agent.complete", new=AsyncMock(return_value="fabricated lead")
            ):
                await agent.run("Find target leads.")

            shared_content = (Path(directory) / "leads.md").read_text(encoding="utf-8")

        self.assertEqual(
            shared_content,
            "| name | handle | contact | why |\n| --- | --- | --- | --- |",
        )
        self.assertTrue(
            any(
                "No matching public posts" in message.text
                for message in bus.history
            )
        )

    async def test_overlapping_runs_keep_discovery_results_task_local(self):
        def make_lead(name):
            return {
                "name": name,
                "handle": f"u/{name.casefold()}",
                "contact": "",
                "source": f"https://www.reddit.com/r/careerguidance/comments/{name}/post/",
                "why": f"Public post for {name}.",
            }

        first_search_started = asyncio.Event()
        second_search_started = asyncio.Event()
        second_search_release = asyncio.Event()
        first_llm_started = asyncio.Event()
        second_llm_started = asyncio.Event()
        llm_release = asyncio.Event()
        captured_writes = []
        search_count = 0
        llm_count = 0

        async def overlapping_search(**_kwargs):
            nonlocal search_count
            search_count += 1
            current_search = search_count
            if current_search == 1:
                first_search_started.set()
                await second_search_started.wait()
                await second_search_release.wait()
                return [make_lead("First")]
            second_search_started.set()
            second_search_release.set()
            await first_search_started.wait()
            return [make_lead("Second")]

        async def overlapping_llm(*_args, **_kwargs):
            nonlocal llm_count
            llm_count += 1
            current_llm = llm_count
            if current_llm == 1:
                first_llm_started.set()
                await second_llm_started.wait()
                await llm_release.wait()
                return "model output"
            second_llm_started.set()
            llm_release.set()
            await first_llm_started.wait()
            return "model output"

        with tempfile.TemporaryDirectory() as directory:
            bus = Bus()
            workspace = Workspace(root=directory, bus=bus)
            agent = LeadGenAgent(SPECS["leads"], workspace, bus)
            original_write = workspace.write

            async def capture_write(name, content, author):
                if name == "leads.md":
                    captured_writes.append(content)
                await original_write(name, content, author)

            workspace.write = capture_write
            with patch("agents.custom.find_leads", new=overlapping_search), patch(
                "agent.complete", new=overlapping_llm
            ):
                await asyncio.gather(
                    agent.run("First idea lead search."),
                    agent.run("Second idea lead search."),
                )

        self.assertEqual(len(captured_writes), 2)
        self.assertTrue(any("| First | u/first |" in content for content in captured_writes))
        self.assertTrue(any("| Second | u/second |" in content for content in captured_writes))
        self.assertFalse(
            any(
                ("| First | u/first |" in content)
                and ("| Second | u/second |" in content)
                for content in captured_writes
            )
        )


if __name__ == "__main__":
    unittest.main()
