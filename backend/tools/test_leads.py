"""Offline tests for public Reddit RSS lead discovery."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.leads import LeadSourceUnavailable, _discover_leads, find_leads


ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>What skills should I learn for a career change?</title>
    <link href="https://www.reddit.com/r/careerguidance/comments/example/post/"/>
    <author><name>u/example_user</name></author>
    <content type="html">&lt;p&gt;Looking for advice on which skills to learn.&lt;/p&gt;</content>
  </entry>
  <entry>
    <title>My weekend project</title>
    <link href="https://www.reddit.com/r/careerguidance/comments/other/post/"/>
    <author><name>u/another_user</name></author>
    <content type="html">&lt;p&gt;I built a small app.&lt;/p&gt;</content>
  </entry>
</feed>
"""


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return ATOM_FEED


class RedditLeadTests(unittest.TestCase):
    def test_discovery_returns_matching_public_post_and_never_email(self):
        requests = []

        def opener(request, *, timeout):
            requests.append((request, timeout))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as directory:
            results_file = Path(directory) / "leads.json"
            with patch("tools.leads.RESULTS_FILE", results_file):
                result = _discover_leads(
                    "skill guidance", "Anywhere", 10, opener=opener
                )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["handle"], "u/example_user")
        self.assertEqual(result[0]["contact"], "")
        self.assertEqual(
            result[0]["source"],
            "https://www.reddit.com/r/careerguidance/comments/example/post/",
        )
        self.assertTrue(requests)
        self.assertTrue(all(timeout == 15 for _, timeout in requests))
        self.assertTrue(all(request.full_url.startswith("https://www.reddit.com/") for request, _ in requests))

    def test_async_backend_entrypoint_uses_discovery(self):
        expected = [{"name": "public post"}]
        with patch("tools.leads.asyncio.to_thread", return_value=expected) as to_thread:
            result = asyncio.run(find_leads("skill coaching", "Anywhere", 3))
        self.assertEqual(result, expected)
        to_thread.assert_called_once()

    def test_rejects_invalid_limit(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            _discover_leads("query", "Anywhere", 0, opener=lambda *_args, **_kwargs: FakeResponse())

    def test_async_entrypoint_returns_empty_on_feed_failures(self):
        with patch(
            "tools.leads._discover_leads",
            side_effect=LeadSourceUnavailable("all feeds unavailable"),
        ):
            result = asyncio.run(find_leads("skill coaching", "Anywhere", 3))
        self.assertEqual(result, [])

    def test_successful_search_saves_current_results_atomically(self):
        config = {
            "subreddits": ["careerguidance"],
            "intent_terms": ["advice"],
            "topic_terms": ["skills"],
            "limit_per_feed": 10,
        }
        feed = [
            {
                "title": "What skills should I learn for career change?",
                "content": "Looking for advice.",
                "url": "https://www.reddit.com/r/careerguidance/comments/example/post/",
                "author": "u/example_user",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            results_file = Path(directory) / "leads.json"
            with patch("tools.leads.RESULTS_FILE", results_file), patch(
                "tools.leads._load_sources", return_value=config
            ), patch("tools.leads._read_feed", return_value=feed):
                result = _discover_leads("query", "Anywhere", 10)
            saved = json.loads(results_file.read_text(encoding="utf-8"))
        self.assertEqual(saved, result)
        self.assertEqual(len(saved), 1)

    def test_successful_search_saves_empty_results_when_no_posts_match(self):
        config = {
            "subreddits": ["careerguidance"],
            "intent_terms": ["advice"],
            "topic_terms": ["skills"],
            "limit_per_feed": 10,
        }
        with tempfile.TemporaryDirectory() as directory:
            results_file = Path(directory) / "leads.json"
            with patch("tools.leads.RESULTS_FILE", results_file), patch(
                "tools.leads._load_sources", return_value=config
            ), patch("tools.leads._read_feed", return_value=[]):
                result = _discover_leads("query", "Anywhere", 10)
            saved = json.loads(results_file.read_text(encoding="utf-8"))
        self.assertEqual(result, [])
        self.assertEqual(saved, [])


if __name__ == "__main__":
    unittest.main()
