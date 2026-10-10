"""Tests for workspace text encoding on Windows and other platforms."""

import tempfile
import unittest
from pathlib import Path

from bus import Bus
from workspace import Workspace


class WorkspaceEncodingTests(unittest.IsolatedAsyncioTestCase):
    async def test_unicode_landing_page_is_saved_with_its_live_url(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(root=directory, bus=Bus())
            content = (
                "<!-- live: https://example.netlify.app -->\n"
                "<html><body>✓ Café</body></html>"
            )

            await workspace.write("landing.md", content, "LandingPage")

            saved = Path(directory, "landing.md").read_bytes()
            self.assertEqual(
                saved.decode("utf-8").replace("\r\n", "\n"),
                content,
            )
            self.assertEqual(workspace.read("landing.md"), content)

    async def test_append_preserves_unicode_and_converts_legacy_windows_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "lessons.md")
            path.write_bytes("Café".encode("cp1252"))
            workspace = Workspace(root=directory, bus=Bus())

            await workspace.append("lessons.md", "Next lesson ✓", "Control")

            self.assertEqual(
                path.read_bytes().decode("utf-8").replace("\r\n", "\n"),
                "Café\nNext lesson ✓",
            )


if __name__ == "__main__":
    unittest.main()
