"""Offline tests for the sandboxed Gmail outreach adapter."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bus import Bus
from control import Control
from tools.outreach import InputValidationError, _message_from_variant, send_dm
from workspace import Workspace


TEST_EMAIL = "demo-inbox@example.com"
TEST_LINK = "https://test-site.netlify.app"
TEST_LEAD = {
    "name": "Test Inbox",
    "email": TEST_EMAIL,
    "offer": "a scheduling tool for independent clinics",
}


class OutreachSenderTests(unittest.TestCase):
    def setUp(self):
        self.landing_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.landing_directory.cleanup)
        self.landing_path_patch = patch(
            "tools.outreach.LANDING_PAGE_FILE",
            Path(self.landing_directory.name) / "landing.md",
        )
        self.landing_path_patch.start()
        self.addCleanup(self.landing_path_patch.stop)

    def test_dry_run_is_default_and_never_calls_sender(self):
        with patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}), patch(
            "tools.outreach.load_suppressions", return_value=set()
        ), patch("tools.outreach.send_batch") as send_batch:
            result = asyncio.run(send_dm(TEST_LEAD, "Sandbox message"))

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["recipient"], TEST_EMAIL)
        self.assertFalse(result["ok"])
        send_batch.assert_not_called()

    def test_live_send_requires_explicit_compliance_confirmation(self):
        with patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}), patch(
            "tools.outreach.load_suppressions", return_value=set()
        ), patch("tools.outreach.send_batch") as send_batch:
            with self.assertRaisesRegex(ValueError, "compliance confirmation"):
                asyncio.run(
                    send_dm(
                        TEST_LEAD,
                        "Sandbox message",
                        dry_run=False,
                    )
                )

        send_batch.assert_not_called()

    def test_live_send_delegates_to_sender_with_results_and_optouts(self):
        sender_result = {
            "recipient": TEST_EMAIL,
            "status": "accepted",
            "provider_message_id": "gmail-test-id",
            "error": None,
        }
        suppressions = {"opted-out@example.com"}
        with patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}), patch(
            "tools.outreach.load_suppressions", return_value=suppressions
        ), patch("tools.outreach.send_batch", return_value=[sender_result]) as send_batch:
            result = asyncio.run(
                send_dm(
                    TEST_LEAD,
                    "Sandbox message",
                    dry_run=False,
                    compliance_confirmed=True,
                )
            )

        self.assertEqual(result["status"], "accepted")
        self.assertTrue(result["ok"])
        self.assertEqual(result["id"], "gmail-test-id")
        arguments = send_batch.call_args
        self.assertEqual(arguments.args[0], [{
            "name": "Test Inbox",
            "email": TEST_EMAIL,
            "message": "Sandbox message",
        }])
        self.assertEqual(arguments.kwargs["suppressed_emails"], suppressions)
        self.assertTrue(arguments.kwargs["compliance_confirmed"])
        self.assertEqual(arguments.kwargs["subject"], "A quick introduction")

    def test_rejects_non_allowlisted_recipient_before_sender_call(self):
        other_lead = {"name": "Other", "email": "other@example.com"}
        with patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}), patch(
            "tools.outreach.load_suppressions", return_value=set()
        ), patch("tools.outreach.send_batch") as send_batch:
            with self.assertRaisesRegex(PermissionError, "restricted"):
                asyncio.run(
                    send_dm(
                        other_lead,
                        "Message",
                        dry_run=False,
                        compliance_confirmed=True,
                    )
                )

        send_batch.assert_not_called()

    def test_reddit_username_cannot_be_used_as_email(self):
        with patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}):
            with self.assertRaises(InputValidationError):
                asyncio.run(send_dm({"handle": "u/example_user"}, "Message"))

    def test_lead_contact_field_is_used_as_email_address(self):
        with patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}), patch(
            "tools.outreach.load_suppressions", return_value=set()
        ), patch("tools.outreach.send_batch") as send_batch:
            result = asyncio.run(
                send_dm(
                    {"name": "Test Inbox", "contact": TEST_EMAIL},
                    "Sandbox message",
                )
            )

        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["recipient"], TEST_EMAIL)
        send_batch.assert_not_called()

    def test_opted_out_test_recipient_is_skipped(self):
        sender_result = {
            "recipient": TEST_EMAIL,
            "status": "skipped",
            "provider_message_id": None,
            "error": "Recipient is present in the opt-out suppression list.",
        }
        with patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}), patch(
            "tools.outreach.load_suppressions",
            return_value={TEST_EMAIL.casefold()},
        ), patch("tools.outreach.send_batch", return_value=[sender_result]) as send_batch:
            result = asyncio.run(
                send_dm(
                    TEST_LEAD,
                    "Sandbox message",
                    dry_run=False,
                    compliance_confirmed=True,
                )
            )

        self.assertEqual(result["status"], "skipped")
        self.assertTrue(send_batch.called)

    def test_message_can_be_loaded_and_personalized_from_variants_json(self):
        variants = {
            "A": {"angle": "pain-point", "subject": "A practical idea", "text": "Hi {name},\n\nI am reaching out about {offer}.\n\n{link}"},
            "B": {"angle": "social-proof", "subject": "An approach to explore", "text": "Hi {name},\n\nI am exploring {offer}.\n\n{link}"},
            "C": {"angle": "question", "subject": "A quick question", "text": "Hi {name},\n\nCould {offer} help your team?\n\n{link}"},
            "D": {"angle": "offer-first", "subject": "A useful idea to share", "text": "Hi {name},\n\nI am building {offer}.\n\n{link}"},
        }
        with tempfile.TemporaryDirectory() as directory:
            variants_file = Path(directory) / "variants.json"
            variants_file.write_text(json.dumps(variants), encoding="utf-8")
            result = _message_from_variant(
                {
                    "name": "Jamie",
                    "offer": "a scheduling tool for independent clinics",
                    "why": "internal search note must not appear",
                },
                "C",
                variants_file,
                TEST_LINK,
            )

        self.assertEqual(
            result,
            f"Hi Jamie,\n\nCould a scheduling tool for independent clinics help your team?\n\n{TEST_LINK}",
        )

    def test_legacy_variant_without_link_placeholder_appends_live_url(self):
        variants = {
            "A": {"angle": "pain-point", "subject": "A practical idea", "text": "Hi {name},\n\nI am reaching out about {offer}."},
            "B": {"angle": "social-proof", "subject": "An approach to explore", "text": "Hi {name},\n\nI am exploring {offer}.\n\n{link}"},
            "C": {"angle": "question", "subject": "A quick question", "text": "Hi {name},\n\nCould {offer} help your team?\n\n{link}"},
            "D": {"angle": "offer-first", "subject": "A useful idea to share", "text": "Hi {name},\n\nI am building {offer}.\n\n{link}"},
        }
        with tempfile.TemporaryDirectory() as directory:
            variants_file = Path(directory) / "variants.json"
            variants_file.write_text(json.dumps(variants), encoding="utf-8")

            message = _message_from_variant(
                TEST_LEAD,
                "A",
                variants_file,
                TEST_LINK,
            )

        self.assertTrue(message.endswith(f"\n\n{TEST_LINK}"))

    def test_send_dm_uses_variant_message_for_sandbox_sender(self):
        variants = {
            "A": {"angle": "pain-point", "subject": "A practical idea", "text": "Hi {name},\n\nI am reaching out about {offer}.\n\n{link}"},
            "B": {"angle": "social-proof", "subject": "An approach to explore", "text": "Hi {name},\n\nI am exploring {offer}.\n\n{link}"},
            "C": {"angle": "question", "subject": "A quick question", "text": "Hi {name},\n\nCould {offer} help your team?\n\n{link}"},
            "D": {"angle": "offer-first", "subject": "A useful idea to share", "text": "Hi {name},\n\nI am building {offer}.\n\n{link}"},
        }
        sender_result = {
            "recipient": TEST_EMAIL,
            "status": "accepted",
            "provider_message_id": "gmail-variant-id",
            "error": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            variants_file = Path(directory) / "variants.json"
            variants_file.write_text(json.dumps(variants), encoding="utf-8")
            with patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}), patch(
                "tools.outreach.load_suppressions", return_value=set()
            ), patch("tools.outreach.send_batch", return_value=[sender_result]) as send_batch:
                result = asyncio.run(
                    send_dm(
                        {
                            "name": "Jamie",
                            "why": "internal search note must not appear",
                            "offer": "a scheduling tool for independent clinics",
                            "email": TEST_EMAIL,
                        },
                        variant="C",
                        variants_file=variants_file,
                        landing_url=TEST_LINK,
                        dry_run=False,
                        compliance_confirmed=True,
                    )
                )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(
            send_batch.call_args.args[0][0]["message"],
            f"Hi Jamie,\n\nCould a scheduling tool for independent clinics help your team?\n\n{TEST_LINK}",
        )
        self.assertEqual(send_batch.call_args.kwargs["subject"], "A quick question")

    def test_landing_page_url_is_added_at_the_end_of_email(self):
        landing_url = "https://example-site.netlify.app"
        sender_result = {
            "recipient": TEST_EMAIL,
            "status": "accepted",
            "provider_message_id": "gmail-landing-link-id",
            "error": None,
        }
        with patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}), patch(
            "tools.outreach.load_suppressions", return_value=set()
        ), patch("tools.outreach.send_batch", return_value=[sender_result]) as send_batch:
            result = asyncio.run(
                send_dm(
                    TEST_LEAD,
                    "A short introduction.",
                    landing_url=landing_url,
                    dry_run=False,
                    compliance_confirmed=True,
                )
            )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(
            send_batch.call_args.args[0][0]["message"],
            f"A short introduction.\n\n{landing_url}",
        )

    def test_live_workspace_landing_page_is_added_when_caller_omits_url(self):
        landing_url = "https://example-site.netlify.app"
        sender_result = {
            "recipient": TEST_EMAIL,
            "status": "accepted",
            "provider_message_id": "gmail-workspace-landing-link-id",
            "error": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            landing_file = Path(directory) / "landing.md"
            landing_file.write_bytes(
                f"<!-- live: {landing_url} -->\n<html>\u2014</html>".encode(
                    "cp1252"
                )
            )
            with (
                patch("tools.outreach.LANDING_PAGE_FILE", landing_file),
                patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}),
                patch("tools.outreach.load_suppressions", return_value=set()),
                patch(
                    "tools.outreach.send_batch",
                    return_value=[sender_result],
                ) as send_batch,
            ):
                result = asyncio.run(
                    send_dm(
                        TEST_LEAD,
                        "A short introduction.",
                        dry_run=False,
                        compliance_confirmed=True,
                    )
                )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(
            send_batch.call_args.args[0][0]["message"],
            f"A short introduction.\n\n{landing_url}",
        )

    def test_landing_page_url_must_be_https(self):
        with self.assertRaisesRegex(ValueError, "absolute HTTPS URL"):
            asyncio.run(
                send_dm(TEST_LEAD, "A short introduction.", landing_url="http://example.com")
            )

    def test_control_passes_deployed_workspace_url_to_outreach(self):
        landing_url = "https://control-test.netlify.app"
        with tempfile.TemporaryDirectory() as directory:
            workspace = Workspace(root=directory, bus=Bus())
            (Path(directory) / "landing.md").write_text(
                f"<!-- live: {landing_url} -->\n<html></html>",
                encoding="utf-8",
            )
            with patch("control.Experiments"):
                control = Control(workspace, workspace.bus)
            control.exp.allocate.return_value = ["A"]
            control.exp.stats.return_value = {}
            control.exp.winner.return_value = None
            control.gate = AsyncMock(return_value=True)
            control.say = AsyncMock()
            control._load_leads_for_outreach = lambda: []
            control.simulate_reply = AsyncMock(return_value=False)
            control.learn_round = AsyncMock()
            workspace.append = AsyncMock()

            with (
                patch.dict("os.environ", {"OUTREACH_TEST_EMAIL": TEST_EMAIL}),
                patch(
                    "tools.outreach.send_dm",
                    new=AsyncMock(return_value={"ok": False, "status": "dry_run"}),
                ) as send_dm_mock,
            ):
                asyncio.run(control.run_round(1))

        self.assertEqual(
            send_dm_mock.await_args.kwargs["landing_url"],
            landing_url,
        )

    def test_invalid_variant_is_rejected(self):
        variants = {
            "A": {"angle": "pain-point", "subject": "A practical idea", "text": "Hi {name},\n\nI am reaching out about {offer}.\n\n{link}"},
            "B": {"angle": "social-proof", "subject": "An approach to explore", "text": "Hi {name},\n\nI am exploring {offer}.\n\n{link}"},
            "C": {"angle": "question", "subject": "A quick question", "text": "Hi {name},\n\nCould {offer} help your team?\n\n{link}"},
            "D": {"angle": "offer-first", "subject": "A useful idea to share", "text": "Hi {name},\n\nI am building {offer}.\n\n{link}"},
        }
        with tempfile.TemporaryDirectory() as directory:
            variants_file = Path(directory) / "variants.json"
            variants_file.write_text(json.dumps(variants), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not present"):
                _message_from_variant(TEST_LEAD, "E", variants_file)

    def test_challenger_variant_is_loaded_from_json(self):
        variants = {
            "A": {"angle": "pain-point", "subject": "A practical idea", "text": "Hi {name},\n\nI am reaching out about {offer}.\n\n{link}"},
            "B": {"angle": "social-proof", "subject": "An approach to explore", "text": "Hi {name},\n\nI am exploring {offer}.\n\n{link}"},
            "C": {"angle": "question", "subject": "A quick question", "text": "Hi {name},\n\nCould {offer} help your team?\n\n{link}"},
            "D": {"angle": "offer-first", "subject": "A useful idea to share", "text": "Hi {name},\n\nI am building {offer}.\n\n{link}"},
            "E": {"angle": "curiosity-led", "subject": "A question for you", "text": "Hi {name},\n\nI am exploring {offer}. What would you change?\n\n{link}"},
            "F": {"angle": "proof-led", "subject": "A practical overview", "text": "Hi {name},\n\nMay I share an overview of {offer}?\n\n{link}"},
        }
        with tempfile.TemporaryDirectory() as directory:
            variants_file = Path(directory) / "variants.json"
            variants_file.write_text(json.dumps(variants), encoding="utf-8")
            result = _message_from_variant(
                {
                    "name": "Jamie",
                    "offer": "a scheduling tool for independent clinics",
                    "why": "internal search note must not appear",
                },
                "E",
                variants_file,
                TEST_LINK,
            )

        self.assertEqual(
            result,
            f"Hi Jamie,\n\nI am exploring a scheduling tool for independent clinics. What would you change?\n\n{TEST_LINK}",
        )

    def test_legacy_why_placeholder_is_rejected_before_sending(self):
        variants = {
            "A": {"angle": "pain-point", "subject": "A practical idea", "text": "Hi {name}, {why} {offer} {link}"},
            "B": {"angle": "social-proof", "subject": "An approach to explore", "text": "Hi {name},\n\nI am exploring {offer}.\n\n{link}"},
            "C": {"angle": "question", "subject": "A quick question", "text": "Hi {name},\n\nCould {offer} help your team?\n\n{link}"},
            "D": {"angle": "offer-first", "subject": "A useful idea to share", "text": "Hi {name},\n\nI am building {offer}.\n\n{link}"},
        }
        with tempfile.TemporaryDirectory() as directory:
            variants_file = Path(directory) / "variants.json"
            variants_file.write_text(json.dumps(variants), encoding="utf-8")
            with patch("tools.outreach.send_batch") as send_batch:
                with self.assertRaisesRegex(ValueError, "Regenerate variants.json"):
                    asyncio.run(
                        send_dm(
                            TEST_LEAD,
                            variant="A",
                            variants_file=variants_file,
                            landing_url=TEST_LINK,
                        )
                    )
        send_batch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
