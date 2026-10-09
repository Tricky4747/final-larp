"""Reusable Gmail API email sender."""

from .sender import (
    AuthorizationSetupError,
    InputValidationError,
    load_records,
    load_suppressions,
    main,
    send_batch,
    send_email,
    validate_email_address,
    validate_records,
)

__all__ = [
    "AuthorizationSetupError",
    "InputValidationError",
    "load_records",
    "load_suppressions",
    "main",
    "send_batch",
    "send_email",
    "validate_email_address",
    "validate_records",
]
