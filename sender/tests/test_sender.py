import base64
import contextlib
import email
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httplib2
from googleapiclient.errors import HttpError

from sender import (
    AuthorizationSetupError,
    InputValidationError,
    load_records,
    main,
    send_batch,
    send_email,
)
from sender.sender import _build_gmail_service


RECIPIENT = "recipient@example.com"
RECORDS = [
    {"name": "First Recipient", "email": RECIPIENT, "message": "Hello, recipient."},
    {"name": "Second Recipient", "email": "second@example.com", "message": "A second message."},
]


class FakeSendRequest:
    def __init__(self, service):
        self.service = service
        self.arguments = None

    def send(self, **kwargs):
        self.arguments = kwargs
        return self

    def execute(self):
        return self.service.execute()


class FakeGmailService:
    def __init__(self, execute_responses=None):
        self.execute_responses = iter(execute_responses or [{"id": "gmail-msg-1"}])
        self.request = FakeSendRequest(self)
        self.calls = []

    def users(self):
        return self

    def messages(self):
        return self

    def send(self, **kwargs):
        self.calls.append(("send", kwargs))
        return self.request.send(**kwargs)

    def execute(self):
        self.calls.append(("execute",))
        response = next(self.execute_responses)
        if isinstance(response, BaseException):
            raise response
        return response


def api_error(status, content):
    return HttpError(
        httplib2.Response({"status": str(status)}),
        content.encode("utf-8"),
    )


class SenderTests(unittest.TestCase):
    def test_load_records_accepts_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "emails.json"
            file_path.write_text(json.dumps(RECORDS), encoding="utf-8")
            self.assertEqual(load_records(file_path), RECORDS)

    def test_load_records_rejects_malformed_json_and_records(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "emails.json"
            file_path.write_text("[not valid JSON", encoding="utf-8")
            with self.assertRaises(InputValidationError):
                load_records(file_path)

            invalid_data = [
                {"name": "Recipient", "email": "bad", "message": "Hello"},
                {"name": "Recipient", "email": RECIPIENT},
                {"name": "Recipient", "email": RECIPIENT, "message": "   "},
                {"name": "Recipient", "email": RECIPIENT, "message": "Hello", "extra": True},
                {"name": " ", "email": RECIPIENT, "message": "Hello"},
            ]
            for item in invalid_data:
                with self.subTest(item=item):
                    file_path.write_text(json.dumps([item]), encoding="utf-8")
                    with self.assertRaises(InputValidationError):
                        load_records(file_path)

    def test_successful_send_encodes_plain_text_and_uses_me(self):
        service = FakeGmailService([{"id": "gmail-msg-123"}])
        result = send_email(
            RECIPIENT, "Hello, \N{SNOWMAN}!", service, subject="Test subject"
        )

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["provider_message_id"], "gmail-msg-123")
        self.assertIsNone(result["error"])
        self.assertIsNotNone(result["timestamp"])
        self.assertEqual(
            service.request.arguments["userId"],
            "me",
        )
        raw = service.request.arguments["body"]["raw"]
        self.assertEqual(base64.urlsafe_b64encode(base64.urlsafe_b64decode(raw)).decode(), raw)
        mime_message = email.message_from_bytes(base64.urlsafe_b64decode(raw))
        self.assertEqual(mime_message["To"], RECIPIENT)
        self.assertEqual(mime_message["Subject"], "Test subject")
        self.assertEqual(mime_message.get_content_type(), "text/plain")
        self.assertIn("Hello, \N{SNOWMAN}!", mime_message.get_payload(decode=True).decode())

    def test_api_authentication_error_is_failed_with_reauthorization_hint(self):
        service = FakeGmailService(
            [api_error(401, '{"error":{"message":"Invalid Credentials"}}')]
        )
        result = send_email(RECIPIENT, "Hello", service)
        self.assertEqual(result["status"], "failed")
        self.assertIn("HTTP 401", result["error"])
        self.assertIn("token.json", result["error"])

    def test_api_quota_error_is_failed_and_reported(self):
        service = FakeGmailService(
            [api_error(403, '{"error":{"message":"Rate Limit Exceeded"}}')]
        )
        result = send_email(RECIPIENT, "Hello", service)
        self.assertEqual(result["status"], "failed")
        self.assertIn("HTTP 403", result["error"])
        self.assertIn("quota", result["error"])
        self.assertIn("Rate Limit Exceeded", result["error"])

    def test_network_failure_is_unknown_and_not_retried(self):
        service = FakeGmailService([httplib2.ServerNotFoundError("timeout")])
        result = send_email(RECIPIENT, "Hello", service)
        self.assertEqual(result["status"], "unknown")
        self.assertIn("no automatic retry", result["error"])
        self.assertEqual(
            [call[0] for call in service.calls].count("execute"),
            1,
        )

    def test_batch_honors_opt_out_without_api_calls(self):
        service = FakeGmailService()
        with tempfile.TemporaryDirectory() as directory:
            results_path = Path(directory) / "results.json"
            results = send_batch(
                RECORDS,
                gmail_service=service,
                results_path=results_path,
                suppressed_emails={RECIPIENT.upper(), "SECOND@example.com"},
                compliance_confirmed=True,
            )
            saved = json.loads(results_path.read_text(encoding="utf-8"))

        self.assertEqual([row["status"] for row in results], ["skipped", "skipped"])
        self.assertEqual(saved, results)
        self.assertIsNone(results[0]["provider_message_id"])
        self.assertFalse(service.calls)

    def test_all_opted_out_batch_does_not_start_oauth(self):
        service_factory = Mock(side_effect=AssertionError("OAuth started"))
        with tempfile.TemporaryDirectory() as directory:
            results = send_batch(
                RECORDS,
                results_path=Path(directory) / "results.json",
                suppressed_emails={RECIPIENT.casefold(), "second@example.com"},
                service_factory=service_factory,
                compliance_confirmed=True,
            )
        self.assertEqual([row["status"] for row in results], ["skipped", "skipped"])
        service_factory.assert_not_called()

    def test_batch_persists_first_send_before_next_send(self):
        service = FakeGmailService(
            [{"id": "gmail-msg-2"}, {"id": "gmail-msg-3"}]
        )
        with tempfile.TemporaryDirectory() as directory:
            results_path = Path(directory) / "results.json"
            persistence_snapshots = []
            original_execute = service.execute
            execute_count = 0

            def execute_and_check():
                nonlocal execute_count
                execute_count += 1
                if execute_count == 2:
                    persistence_snapshots.append(
                        json.loads(results_path.read_text(encoding="utf-8"))
                    )
                return original_execute()

            service.execute = execute_and_check
            results = send_batch(
                RECORDS,
                gmail_service=service,
                results_path=results_path,
                compliance_confirmed=True,
            )

        self.assertEqual([row["status"] for row in results], ["accepted", "accepted"])
        self.assertEqual(persistence_snapshots, [[results[0]]])

    def test_api_rejection_does_not_stop_later_recipient(self):
        service = FakeGmailService(
            [api_error(403, '{"error":{"message":"Quota exceeded"}}'), {"id": "ok-2"}]
        )
        with tempfile.TemporaryDirectory() as directory:
            results = send_batch(
                RECORDS,
                gmail_service=service,
                results_path=Path(directory) / "results.json",
                compliance_confirmed=True,
            )

        self.assertEqual([row["status"] for row in results], ["failed", "accepted"])
        self.assertEqual(results[1]["provider_message_id"], "ok-2")

    def test_auth_setup_failure_is_logged_for_recipients_but_keeps_opt_out(self):
        with tempfile.TemporaryDirectory() as directory:
            results_path = Path(directory) / "results.json"

            def fail_auth():
                raise AuthorizationSetupError("OAuth consent is required.")

            results = send_batch(
                RECORDS,
                results_path=results_path,
                suppressed_emails={RECIPIENT.casefold()},
                service_factory=fail_auth,
                compliance_confirmed=True,
            )
            saved = json.loads(results_path.read_text(encoding="utf-8"))

        self.assertEqual([row["status"] for row in results], ["skipped", "failed"])
        self.assertIn("OAuth consent is required", results[1]["error"])
        self.assertEqual(saved, results)

    def test_batch_requires_compliance_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Confirm that each recipient"):
                send_batch(RECORDS, results_path=Path(directory) / "results.json")

    def test_invalid_batch_is_rejected_before_service_creation(self):
        service_factory = Mock(side_effect=AssertionError("OAuth started"))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(InputValidationError):
                send_batch(
                    [
                        RECORDS[0],
                        {"name": "Invalid", "email": "invalid", "message": "Hello"},
                    ],
                    results_path=Path(directory) / "results.json",
                    service_factory=service_factory,
                    compliance_confirmed=True,
                )
            self.assertFalse((Path(directory) / "results.json").exists())
        service_factory.assert_not_called()

    def test_dry_run_never_starts_oauth_or_sends(self):
        with tempfile.TemporaryDirectory() as directory:
            email_file = Path(directory) / "emails.json"
            opt_outs_file = Path(directory) / "opt-outs.json"
            email_file.write_text(json.dumps(RECORDS), encoding="utf-8")
            opt_outs_file.write_text("[]", encoding="utf-8")
            stdout = io.StringIO()
            with patch("sender.sender._build_gmail_service") as service_builder:
                with contextlib.redirect_stdout(stdout):
                    status = main(
                        [
                            "--file",
                            str(email_file),
                            "--opt-outs",
                            str(opt_outs_file),
                            "--dry-run",
                        ]
                    )
            self.assertEqual(status, 0)
            self.assertIn("Validated 2 email(s)", stdout.getvalue())
            service_builder.assert_not_called()

    def test_oauth_flow_requests_send_scope_and_saves_token(self):
        credentials = Mock(valid=True, expired=False)
        credentials.to_json.return_value = '{"token":"test"}'
        flow = Mock()
        flow.run_local_server.return_value = credentials
        flow_factory = Mock(return_value=flow)
        service = object()
        service_builder = Mock(return_value=service)

        with tempfile.TemporaryDirectory() as directory:
            credentials_path = Path(directory) / "credentials.json"
            token_path = Path(directory) / "token.json"
            credentials_path.write_text("{}", encoding="utf-8")
            actual_service = _build_gmail_service(
                credentials_path,
                token_path,
                flow_factory=flow_factory,
                service_builder=service_builder,
            )

            self.assertIs(actual_service, service)
            self.assertEqual(json.loads(token_path.read_text(encoding="utf-8")), {"token": "test"})
            flow_factory.assert_called_once()
            self.assertEqual(flow_factory.call_args.args[1], [
                "https://www.googleapis.com/auth/gmail.send"
            ])
            flow.run_local_server.assert_called_once_with(port=0)
            service_builder.assert_called_once()

    def test_expired_oauth_token_is_refreshed(self):
        credentials = Mock(valid=True, expired=True, refresh_token="refresh-token")
        credentials.to_json.return_value = '{"token":"refreshed"}'
        with tempfile.TemporaryDirectory() as directory:
            credentials_path = Path(directory) / "credentials.json"
            token_path = Path(directory) / "token.json"
            credentials_path.write_text("{}", encoding="utf-8")
            token_path.write_text("{}", encoding="utf-8")
            request = object()
            request_factory = Mock(return_value=request)
            service = object()
            service_builder = Mock(return_value=service)
            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=credentials,
            ) as credentials_loader:
                actual_service = _build_gmail_service(
                    credentials_path,
                    token_path,
                    request_factory=request_factory,
                    service_builder=service_builder,
                )

        self.assertIs(actual_service, service)
        credentials_loader.assert_called_once_with(
            str(token_path), ["https://www.googleapis.com/auth/gmail.send"]
        )
        credentials.refresh.assert_called_once_with(request)
        request_factory.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
