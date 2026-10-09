"""Send personalized messages through the Gmail API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import EmailPolicy
from pathlib import Path
from typing import Any, Callable

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import httplib2

import httplib2
from googleapiclient.errors import HttpError

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"
PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIALS_FILE = PROJECT_DIRECTORY / "credentials.json"
DEFAULT_TOKEN_FILE = PROJECT_DIRECTORY / "token.json"
SUBJECT = "A quick introduction"
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


class InputValidationError(ValueError):
    """Raised when an input file does not match the expected format."""


class AuthorizationSetupError(RuntimeError):
    """Raised when Gmail API credentials cannot be prepared."""


def validate_email_address(value: object, field_name: str = "email") -> str:
    if not isinstance(value, str):
        raise InputValidationError(f"{field_name} must be a string.")
    address = value.strip()
    if (
        not address
        or len(address) > 254
        or not EMAIL_PATTERN.fullmatch(address)
        or ".." in address
        or address.startswith(".")
        or address.split("@", 1)[0].endswith(".")
    ):
        raise InputValidationError(f"{field_name} is not a valid email address.")
    return address


def validate_records(data: object) -> list[dict[str, str]]:
    if not isinstance(data, list):
        raise InputValidationError("The JSON root must be a list of email objects.")

    records: list[dict[str, str]] = []
    for index, item in enumerate(data):
        prefix = f"Item {index + 1}"
        if not isinstance(item, dict) or set(item) != {"email", "message", "name"}:
            raise InputValidationError(
                f"{prefix} must contain exactly the 'email', 'message', and "
                "'name' fields."
            )
        address = validate_email_address(item["email"], f"{prefix} email")
        message = item["message"]
        if not isinstance(message, str) or not message.strip():
            raise InputValidationError(f"{prefix} message must be a non-empty string.")
        name = item["name"]
        if not isinstance(name, str) or not name.strip():
            raise InputValidationError(f"{prefix} name must be a non-empty string.")
        records.append({"email": address, "message": message, "name": name.strip()})
    return records


def load_records(file_path: str | Path) -> list[dict[str, str]]:
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputValidationError(f"Invalid JSON in {file_path}: {exc.msg}.") from exc
    except OSError as exc:
        raise InputValidationError(f"Cannot read {file_path}: {exc}.") from exc
    return validate_records(data)


def load_suppressions(file_path: str | Path) -> set[str]:
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputValidationError(
            f"Invalid JSON in suppression file {file_path}: {exc.msg}."
        ) from exc
    except OSError as exc:
        raise InputValidationError(
            f"Cannot read suppression file {file_path}: {exc}."
        ) from exc

    if not isinstance(data, list):
        raise InputValidationError("The suppression file must contain a JSON list.")
    return {
        validate_email_address(value, f"Suppression item {index + 1}")
        .casefold()
        for index, value in enumerate(data)
    }


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_subject(subject: str) -> str:
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("subject must be a non-empty string.")
    if "\r" in subject or "\n" in subject:
        raise ValueError("subject must not contain line breaks.")
    return subject


def _result(
    email: str,
    status: str,
    provider_message_id: str | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "recipient": email,
        "status": status,
        "timestamp": _timestamp(),
        "provider_message_id": provider_message_id,
        "error": error,
    }


def _build_gmail_service(
    credentials_file: str | Path = DEFAULT_CREDENTIALS_FILE,
    token_file: str | Path = DEFAULT_TOKEN_FILE,
    *,
    flow_factory: Callable[..., Any] | None = None,
    request_factory: Callable[[], Any] | None = None,
    service_builder: Callable[..., Any] | None = None,
) -> Any:
    credential_path = Path(credentials_file)
    token_path = Path(token_file)
    if not credential_path.is_file():
        raise AuthorizationSetupError(
            f"OAuth client file not found: {credential_path}. Download a Desktop "
            "OAuth client JSON from Google Cloud Console and save it as "
            "credentials.json in the repository root."
        )

    try:
        credentials = (
            Credentials.from_authorized_user_file(str(token_path), [GMAIL_SCOPE])
            if token_path.is_file()
            else None
        )
    except (OSError, ValueError, GoogleAuthError) as exc:
        raise AuthorizationSetupError(
            f"Could not read {token_path}. Remove the invalid token file and "
            "authorize again."
        ) from exc

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh((request_factory or Request)())
        except Exception:
            credentials = None

    if not credentials or not credentials.valid:
        try:
            flow = (flow_factory or InstalledAppFlow.from_client_secrets_file)(
                str(credential_path), [GMAIL_SCOPE]
            )
            credentials = flow.run_local_server(port=0)
        except Exception:
            raise AuthorizationSetupError(
                "Google OAuth authorization failed. Run the sender again and "
                "complete the browser sign-in and consent flow."
            ) from exc

    token_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    except OSError as exc:
        raise AuthorizationSetupError(f"Could not save OAuth token to {token_path}.") from exc
    try:
        token_path.chmod(0o600)
    except OSError:
        pass

    try:
        return (service_builder or build)(
            "gmail", "v1", credentials=credentials, cache_discovery=False
        )
    except Exception as exc:
        raise AuthorizationSetupError(
            f"Could not initialize the Gmail API client ({type(exc).__name__})."
        ) from exc


def _api_error_detail(exc: Exception) -> str:
    content = getattr(exc, "content", None)
    if isinstance(content, bytes):
        detail = content.decode("utf-8", errors="replace")
    elif content is not None:
        detail = str(content)
    else:
        detail = str(exc)
    return detail[:1000] or type(exc).__name__


def _send_with_service(
    email: str,
    message: str,
    gmail_service: Any,
    subject: str,
) -> dict[str, Any]:
    _NO_WRAP_POLICY = EmailPolicy(utf8=True, max_line_length=None, linesep="\r\n")
    email_message = EmailMessage(policy=_NO_WRAP_POLICY)
    email_message["To"] = email
    email_message["Subject"] = subject
    email_message.set_content(message, subtype="plain", charset="utf-8")
    raw_message = base64.urlsafe_b64encode(email_message.as_bytes()).decode("ascii")

    try:
        response = (
            gmail_service.users()
            .messages()
            .send(userId="me", body={"raw": raw_message})
            .execute()
        )
        provider_id = response.get("id") if isinstance(response, dict) else None
        return _result(
            email,
            "accepted",
            provider_id if isinstance(provider_id, str) else None,
            None,
        )
    except HttpError as exc:
        status_code = getattr(getattr(exc, "resp", None), "status", None)
        detail = _api_error_detail(exc)
        hint = ""
        if status_code == 401:
            hint = " Reauthorize by removing token.json and running the sender again."
        elif status_code == 403:
            hint = " Check Gmail API access, account restrictions, and quota."
        return _result(
            email,
            "failed",
            None,
            f"Gmail API rejected the send (HTTP {status_code}: {detail}).{hint}",
        )
    except GoogleAuthError as exc:
        return _result(
            email,
            "failed",
            None,
            f"Google authorization failed ({type(exc).__name__}). "
            "Remove token.json and run the sender again to reauthorize.",
        )
    except (httplib2.HttpLib2Error, OSError, TimeoutError, ConnectionError) as exc:
        return _result(
            email,
            "unknown",
            None,
            f"Network failure during Gmail API submission "
            f"({type(exc).__name__}: {_api_error_detail(exc)}); acceptance is "
            "uncertain, so no automatic retry was attempted.",
        )


def send_email(
    email: str,
    message: str,
    gmail_service: Any,
    subject: str = SUBJECT,
) -> dict[str, Any]:
    """Send one message through an authorized Gmail API service."""
    address = validate_email_address(email)
    if not isinstance(message, str) or not message.strip():
        raise InputValidationError("message must be a non-empty string.")
    subject = _validate_subject(subject)
    return _send_with_service(address, message, gmail_service, subject)


def _save_results(results_path: Path, results: list[dict[str, Any]]) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=results_path.parent,
            prefix=f".{results_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(results, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, results_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def send_batch(
    records: list[dict[str, str]],
    *,
    results_path: str | Path,
    suppressed_emails: set[str] | None = None,
    subject: str = SUBJECT,
    gmail_service: Any | None = None,
    service_factory: Callable[[], Any] | None = None,
    credentials_file: str | Path = DEFAULT_CREDENTIALS_FILE,
    token_file: str | Path = DEFAULT_TOKEN_FILE,
    compliance_confirmed: bool = False,
) -> list[dict[str, Any]]:
    """Send each validated record and persist each outcome before continuing."""
    validated_records = validate_records(records)
    if not compliance_confirmed:
        raise ValueError(
            "Confirm that each recipient is eligible under applicable consent "
            "requirements and provider policies before sending."
        )
    subject = _validate_subject(subject)
    suppressions = {
        validate_email_address(address, "Suppression email").casefold()
        for address in (suppressed_emails or set())
    }
    output_path = Path(results_path)
    results: list[dict[str, Any]] = []

    def process() -> None:
        _save_results(output_path, results)
        active_service = gmail_service
        if active_service is None:
            pending_records = [
                record
                for record in validated_records
                if record["email"].casefold() not in suppressions
            ]
            if not pending_records:
                for record in validated_records:
                    address = record["email"]
                    results.append(
                        {
                            "recipient": address,
                            "status": "skipped",
                            "timestamp": _timestamp(),
                            "provider_message_id": None,
                            "error": "Recipient is present in the opt-out suppression list.",
                        }
                    )
                    _save_results(output_path, results)
                return
            try:
                active_service = (
                    service_factory()
                    if service_factory is not None
                    else _build_gmail_service(credentials_file, token_file)
                )
            except AuthorizationSetupError as exc:
                for record in validated_records:
                    address = record["email"]
                    if address.casefold() in suppressions:
                        result = {
                            "recipient": address,
                            "status": "skipped",
                            "timestamp": _timestamp(),
                            "provider_message_id": None,
                            "error": "Recipient is present in the opt-out suppression list.",
                        }
                    else:
                        result = _result(address, "failed", None, str(exc))
                    results.append(result)
                    _save_results(output_path, results)
                return

        for record in validated_records:
            address = record["email"]
            if address.casefold() in suppressions:
                result = {
                    "recipient": address,
                    "status": "skipped",
                    "timestamp": _timestamp(),
                    "provider_message_id": None,
                    "error": "Recipient is present in the opt-out suppression list.",
                }
            else:
                try:
                    result = send_email(
                        address,
                        record["message"],
                        active_service,
                        subject=subject,
                    )
                except Exception as exc:
                    result = _result(
                        address,
                        "failed",
                        None,
                        f"Gmail API client error ({type(exc).__name__}: "
                        f"{_api_error_detail(exc)}).",
                    )
            results.append(result)
            _save_results(output_path, results)

    process()
    return results


def _build_parser() -> argparse.ArgumentParser:
    app_directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Send personalized emails through the Gmail API."
    )
    parser.add_argument(
        "--file", default=app_directory / "emails.json", help="Input JSON file."
    )
    parser.add_argument(
        "--results",
        default=app_directory / "results.json",
        help="Incremental results JSON file.",
    )
    parser.add_argument(
        "--opt-outs",
        default=app_directory / "opt-outs.json",
        help="JSON list of addresses that must not be contacted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview emails without sending.",
    )
    parser.add_argument(
        "--compliance-confirmed",
        action="store_true",
        help="Confirm recipients are eligible under applicable law and provider policy.",
    )
    parser.add_argument(
        "--subject", default=SUBJECT, help="Email subject (default: %(default)s)."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        records = load_records(args.file)
        suppressions = load_suppressions(args.opt_outs)
    except InputValidationError as exc:
        parser.error(str(exc))

    if args.dry_run:
        for record in records:
            state = (
                "SUPPRESSED"
                if record["email"].casefold() in suppressions
                else "WOULD SEND"
            )
            print(
                f"{state} to {record['name']} <{record['email']}> "
                f"| Subject: {args.subject}"
            )
            print(record["message"])
            print()
        print(f"Validated {len(records)} email(s); no email was sent.")
        return 0

    if not args.compliance_confirmed:
        parser.error(
            "Live sending requires --compliance-confirmed. Confirm eligibility "
            "and applicable consent requirements for every recipient."
        )

    try:
        results = send_batch(
            records,
            results_path=args.results,
            suppressed_emails=suppressions,
            subject=args.subject,
            compliance_confirmed=True,
        )
    except (InputValidationError, ValueError, AuthorizationSetupError) as exc:
        parser.error(str(exc))

    for result in results:
        print(f"{result['status'].upper()}: {result['recipient']}")
        if result["error"]:
            print(f"  {result['error']}")
    print(f"Saved {len(results)} result(s) to {args.results}.")
    return int(any(result["status"] in {"failed", "unknown"} for result in results))


if __name__ == "__main__":
    sys.exit(main())