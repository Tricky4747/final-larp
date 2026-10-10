"""Offline tests for the sandboxed Gmail outreach adapter."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.outreach import InputValidationError, _message_from_variant, send_dm


TEST_EMAIL = "demo-inbox@example.com"
TEST_LEAD = {"name": "Test Inbox", "email": TEST_EMAIL}


class OutreachSenderTests(unittest.TestCase):
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
            "A": {"angle": "pain-point", "text": "Hi {name}, {why}"},
            "B": {"angle": "social-proof", "text": "Hi {name}, {why}"},
            "C": {"angle": "question", "text": "Hi {name}, {why}"},
            "D": {"angle": "offer-first", "text": "Hi {name}, {why}"},
        }
        with tempfile.TemporaryDirectory() as directory:
            variants_file = Path(directory) / "variants.json"
            variants_file.write_text(json.dumps(variants), encoding="utf-8")
            result = _message_from_variant(
                {"name": "Jamie", "why": "you mentioned learning new skills"},
                "C",
                variants_file,
            )

        self.assertEqual(result, "Hi Jamie, you mentioned learning new skills")

    def test_send_dm_uses_variant_message_for_sandbox_sender(self):
        variants = {
            "A": {"angle": "pain-point", "text": "Hi {name}, {why}"},
            "B": {"angle": "social-proof", "text": "Hi {name}, {why}"},
            "C": {"angle": "question", "text": "Hi {name}, {why}"},
            "D": {"angle": "offer-first", "text": "Hi {name}, {why}"},
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
                        {"name": "Jamie", "why": "you asked for skills advice", "email": TEST_EMAIL},
                        variant="C",
                        variants_file=variants_file,
                        dry_run=False,
                        compliance_confirmed=True,
                    )
                )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(
            send_batch.call_args.args[0][0]["message"],
            "Hi Jamie, you asked for skills advice",
        )

    def test_invalid_variant_is_rejected(self):
        variants = {
            "A": {"angle": "pain-point", "text": "Hi {name}, {why}"},
            "B": {"angle": "social-proof", "text": "Hi {name}, {why}"},
            "C": {"angle": "question", "text": "Hi {name}, {why}"},
            "D": {"angle": "offer-first", "text": "Hi {name}, {why}"},
        }
        with tempfile.TemporaryDirectory() as directory:
            variants_file = Path(directory) / "variants.json"
            variants_file.write_text(json.dumps(variants), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not present"):
                _message_from_variant(TEST_LEAD, "E", variants_file)

    def test_challenger_variant_is_loaded_from_json(self):
        variants = {
            "A": {"angle": "pain-point", "text": "Hi {name}, {why}"},
            "B": {"angle": "social-proof", "text": "Hi {name}, {why}"},
            "C": {"angle": "question", "text": "Hi {name}, {why}"},
            "D": {"angle": "offer-first", "text": "Hi {name}, {why}"},
            "E": {"angle": "curiosity-led", "text": "Hi {name}, {why}"},
            "F": {"angle": "proof-led", "text": "Hi {name}, {why}"},
        }
        with tempfile.TemporaryDirectory() as directory:
            variants_file = Path(directory) / "variants.json"
            variants_file.write_text(json.dumps(variants), encoding="utf-8")
            result = _message_from_variant(
                {"name": "Jamie", "why": "you requested practical advice"},
                "E",
                variants_file,
            )

        self.assertEqual(result, "Hi Jamie, you requested practical advice")


if __name__ == "__main__":
    unittest.main()
