import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from leadgen.lead_scraper import (
    MODULE_DIRECTORY,
    LeadSearchError,
    _resolve_path,
    _search_request,
    _discover,
    deduplicate_leads,
    export_markdown,
    main,
    save_leads,
    search_leads,
    validate_lead,
)


CONFIG = {
    "business_idea": "AI-powered social media content service",
    "target_customer": "Small marketing agencies",
    "location": "India",
    "limit": 20,
}


def listing(name, url, content="Public listing related to small marketing agencies."):
    return {"title": name, "url": url, "content": content}


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.body


class LeadScraperTests(unittest.TestCase):
    def test_validate_lead_requires_exact_fields_and_valid_source(self):
        lead = {
            "name": "Example Studio",
            "handle": "",
            "contact": "",
            "why": "Observed listing evidence. Inference: may be relevant.",
            "where": "https://example.com/about",
        }
        self.assertEqual(validate_lead(lead), lead)
        with self.assertRaises(ValueError):
            validate_lead({**lead, "where": "not-a-url"})
        with self.assertRaises(ValueError):
            validate_lead({**lead, "extra": "not allowed"})
        with self.assertRaises(ValueError):
            validate_lead({**lead, "contact": "not-an-email"})

    def test_deduplicate_by_normalized_business_domain(self):
        leads = [
            {
                "name": "Example",
                "handle": "",
                "contact": "",
                "why": "Evidence A.",
                "where": "https://www.Example.com/about",
            },
            {
                "name": "Example second page",
                "handle": "",
                "contact": "",
                "why": "Evidence B.",
                "where": "https://example.com/contact",
            },
        ]
        self.assertEqual(len(deduplicate_leads(leads)), 1)

    def test_search_leads_uses_configured_api_and_returns_supported_lead(self):
        body = {
            "results": [
                listing(
                    "Example Agency",
                    "https://agency.example/services",
                    "Provides marketing services to small agencies.",
                )
            ]
        }
        opened = []

        def opener(request, timeout):
            opened.append((request, timeout))
            return FakeResponse(body)

        leads, discovered, rejected = _discover(
            CONFIG,
            api_key="test-key",
            opener=opener,
        )
        self.assertEqual(discovered, 1)
        self.assertEqual(rejected, 0)
        self.assertEqual(len(leads), 1)
        self.assertEqual(
            set(leads[0]),
            {"name", "handle", "contact", "why", "where"},
        )
        self.assertEqual(leads[0]["name"], "Example Agency")
        self.assertEqual(leads[0]["contact"], "")
        self.assertEqual(leads[0]["handle"], "")
        self.assertIn("Observed in the search listing", leads[0]["why"])
        self.assertIn("Inference:", leads[0]["why"])
        self.assertEqual(opened[0][1], 15)
        self.assertEqual(opened[0][0].full_url, "https://api.tavily.com/search")
        self.assertEqual(opened[0][0].get_method(), "POST")
        self.assertEqual(json.loads(opened[0][0].data)["api_key"], "test-key")

    def test_api_key_is_not_in_errors(self):
        def opener(request, **_kwargs):
            raise HTTPError(request.full_url, 429, "quota", None, io.BytesIO())

        with self.assertRaisesRegex(LeadSearchError, "quota/access limit") as caught:
            _search_request(
                "query",
                "secret-api-key",
                10,
                opener,
            )
        self.assertNotIn("secret-api-key", str(caught.exception))

    def test_default_paths_resolve_inside_leadgen(self):
        self.assertEqual(
            _resolve_path("lead_search.json"), MODULE_DIRECTORY / "lead_search.json"
        )
        self.assertEqual(_resolve_path("leads.json"), MODULE_DIRECTORY / "leads.json")

    def test_search_timeout_is_reported_without_retry(self):
        attempts = []

        def opener(_request, *, timeout):
            attempts.append(timeout)
            raise TimeoutError("request timed out")

        with self.assertRaisesRegex(LeadSearchError, "TimeoutError"):
            _search_request("query", "synthetic-test-key", 5, opener)
        self.assertEqual(attempts, [15])

    def test_missing_credentials_and_bad_config_fail_clearly(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(LeadSearchError, "TAVILY_API_KEY"):
                search_leads(CONFIG)
        with self.assertRaises(LeadSearchError):
            _discover({**CONFIG, "limit": True}, api_key="x")

    def test_invalid_search_results_are_counted_and_duplicates_removed(self):
        body = {
            "results": [
                listing("One", "https://one.example/"),
                listing("One duplicate", "https://www.one.example/contact"),
                {"url": "https://missing-title.example/"},
            ]
        }

        def opener(_request, *, timeout):
            self.assertEqual(timeout, 15)
            return FakeResponse(body)

        leads, discovered, rejected = _discover(
            CONFIG,
            api_key="test-key",
            opener=opener,
        )
        self.assertEqual(discovered, 3)
        self.assertEqual(rejected, 2)
        self.assertEqual(len(leads), 1)

    def test_save_json_and_markdown(self):
        leads = [
            {
                "name": "Example | Studio",
                "handle": "",
                "contact": "",
                "why": "Observed fact. Inference: may match.",
                "where": "https://example.com",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "leads.json"
            markdown_path = Path(directory) / "leads.md"
            save_leads(leads, json_path)
            export_markdown(leads, markdown_path)
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8")),
                [validate_lead(leads[0])],
            )
            markdown = markdown_path.read_text(encoding="utf-8")
        self.assertIn("| Name | Handle | Contact | Why | Where |", markdown)
        self.assertIn(r"Example \| Studio", markdown)

    def test_cli_reports_counts_and_resolves_paths_from_module_dir(self):
        response_body = {"results": [listing("Example", "https://example.test/")]}
        with tempfile.TemporaryDirectory() as directory:
            config_file = Path(directory) / "config.json"
            output_file = Path(directory) / "leads.json"
            markdown_file = Path(directory) / "leads.md"
            config_file.write_text(json.dumps(CONFIG), encoding="utf-8")
            stdout = io.StringIO()
            with patch(
                "leadgen.lead_scraper._search_request",
                return_value=response_body,
            ), patch.dict(
                "os.environ",
                {"TAVILY_API_KEY": "test"},
            ), patch("sys.stdout", stdout):
                code = main(
                    [
                        "--config",
                        str(config_file),
                        "--output",
                        str(output_file),
                        "--markdown",
                        str(markdown_file),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertTrue(output_file.exists())
            self.assertTrue(markdown_file.exists())
            self.assertIn("Discovered 1 search result(s); rejected 0; saved 1 lead(s)", stdout.getvalue())
if __name__ == "__main__":
    unittest.main()
