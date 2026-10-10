"""Offline unit tests for web-scraping lead discovery in tools/leads.py."""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from backend.tools.leads import (
        _clean_name,
        _contact_links,
        _discover,
        _domain_of,
        _extract_emails,
        _is_skipped,
        _same_site,
        _search,
        find_leads,
    )
except ImportError:
    from tools.leads import (
        _clean_name,
        _contact_links,
        _discover,
        _domain_of,
        _extract_emails,
        _is_skipped,
        _same_site,
        _search,
        find_leads,
    )


class TestLeadHelpers(unittest.TestCase):
    def test_domain_of(self):
        self.assertEqual(_domain_of("https://www.example.com/about"), "example.com")
        self.assertEqual(_domain_of("http://sub.domain.co.in/page"), "sub.domain.co.in")
        self.assertEqual(_domain_of("not-a-url"), "")

    def test_is_skipped(self):
        self.assertTrue(_is_skipped("justdial.com"))
        self.assertTrue(_is_skipped("sub.linkedin.com"))
        self.assertTrue(_is_skipped("reddit.com"))
        self.assertFalse(_is_skipped("freshcateringchennai.com"))

    def test_clean_name(self):
        self.assertEqual(_clean_name("ABC Catering | Best Wedding Caterers", "abccatering.com"), "ABC Catering")
        self.assertEqual(_clean_name("XYZ Foods - Chennai", "xyzfoods.in"), "XYZ Foods")
        self.assertEqual(_clean_name("", "xyzfoods.in"), "xyzfoods.in")

    def test_extract_emails_direct_and_obfuscated(self):
        html = """
        <div>
            Contact us: orders@chennaicatering.com
            Alternative: support [at] chennaicatering [dot] com
            Junk: test@example.com, icon@2x.png, info@godaddy.com
        </div>
        """
        emails = _extract_emails(html)
        self.assertIn("orders@chennaicatering.com", emails)
        self.assertIn("support@chennaicatering.com", emails)
        self.assertNotIn("test@example.com", emails)
        self.assertNotIn("icon@2x.png", emails)
        self.assertNotIn("info@godaddy.com", emails)

    def test_same_site_priority(self):
        self.assertTrue(_same_site("info@mycatering.com", "mycatering.com"))
        self.assertTrue(_same_site("info@mycatering.com", "www.mycatering.com"))
        self.assertFalse(_same_site("caterer@gmail.com", "mycatering.com"))

    def test_contact_links(self):
        html = """
        <html>
            <body>
                <a href="/contact-us">Contact</a>
                <a href="https://mysite.com/about">About Us</a>
                <a href="https://external.com/contact">Other</a>
                <a href="mailto:info@mysite.com">Email</a>
            </body>
        </html>
        """
        links = _contact_links(html, "https://mysite.com")
        self.assertIn("https://mysite.com/contact-us", links)
        self.assertIn("https://mysite.com/about", links)
        self.assertNotIn("https://external.com/contact", links)
        self.assertNotIn("mailto:info@mysite.com", links)


class TestValidationAndSearch(unittest.TestCase):
    def test_input_validation(self):
        with self.assertRaises(ValueError):
            asyncio.run(find_leads("", "Chennai", 5))
        with self.assertRaises(ValueError):
            asyncio.run(find_leads("catering", "", 5))
        with self.assertRaises(ValueError):
            asyncio.run(find_leads("catering", "Chennai", 0))
        with self.assertRaises(ValueError):
            asyncio.run(find_leads("catering", "Chennai", -1))
        with self.assertRaises(ValueError):
            asyncio.run(find_leads("catering", "Chennai", True))  # type: ignore

    def test_search_uses_tavily_when_configured(self):
        target_mod = "backend.tools.leads" if "backend.tools.leads" in sys.modules else "tools.leads"
        with patch.dict("os.environ", {"TAVILY_API_KEY": "fake-tavily-key"}):
            with patch(f"{target_mod}._tavily_search") as mock_tavily:
                mock_tavily.return_value = [{"title": "Test", "url": "https://test.com", "snippet": "foo"}]
                results = _search("catering Chennai")
                self.assertEqual(len(results), 1)
                mock_tavily.assert_called_once()

    def test_search_requires_tavily_key_and_does_not_use_alternatives(self):
        target_mod = "backend.tools.leads" if "backend.tools.leads" in sys.modules else "tools.leads"
        with patch.dict("os.environ", {"TAVILY_API_KEY": "", "BRAVE_API_KEY": "ignored"}):
            with patch(f"{target_mod}._tavily_search") as mock_tavily:
                with self.assertRaisesRegex(RuntimeError, "Tavily is the only"):
                    _search("catering Chennai")
                mock_tavily.assert_not_called()

    def test_tavily_empty_results_are_returned_without_fallback(self):
        target_mod = "backend.tools.leads" if "backend.tools.leads" in sys.modules else "tools.leads"
        with patch.dict("os.environ", {"TAVILY_API_KEY": "fake-tavily-key"}):
            with patch(f"{target_mod}._tavily_search", return_value=[]) as mock_tavily:
                self.assertEqual(_search("catering Chennai"), [])
                mock_tavily.assert_called_once()


class TestDiscoveryWorkflow(unittest.TestCase):
    def test_discover_merges_and_saves_leads(self):
        target_mod = "backend.tools.leads" if "backend.tools.leads" in sys.modules else "tools.leads"

        search_results = [
            {"title": "Subiksham Catering | Chennai", "url": "https://www.subikshamcatering.com", "snippet": "Best caterers"},
        ]
        homepage_html = """
        <html>
            <body>
                <h1>Subiksham Catering</h1>
                <p>Email: contact@subikshamcatering.com</p>
            </body>
        </html>
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_leads_file = Path(temp_dir) / "leads.json"
            temp_leads_file.write_text("[]", encoding="utf-8")

            with patch(f"{target_mod}.RESULTS_FILE", temp_leads_file), \
                 patch(f"{target_mod}._search", return_value=search_results), \
                 patch(f"{target_mod}._fetch", return_value=homepage_html), \
                 patch("urllib.robotparser.RobotFileParser.can_fetch", return_value=True):

                leads = asyncio.run(find_leads("catering", "Chennai", 1))

                self.assertEqual(len(leads), 1)
                self.assertEqual(leads[0]["name"], "Subiksham Catering")
                self.assertEqual(leads[0]["handle"], "subikshamcatering.com")
                self.assertEqual(leads[0]["contact"], "contact@subikshamcatering.com")
                self.assertEqual(leads[0]["source"], "https://www.subikshamcatering.com")

                # Verify saved file
                saved_content = json.loads(temp_leads_file.read_text(encoding="utf-8"))
                self.assertEqual(len(saved_content), 1)
                self.assertEqual(saved_content[0]["contact"], "contact@subikshamcatering.com")


if __name__ == "__main__":
    unittest.main()
