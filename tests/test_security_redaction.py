"""Regression tests for credential-safe logging and client errors."""

import logging

from src.security.redaction import (
    SensitiveDataFormatter,
    public_error_message,
    redact_sensitive_text,
)


def test_redacts_named_credentials_and_authorization_headers():
    text = "POSTGRES_PASSWORD=not-a-real-password Authorization: Bearer not-a-real-token"

    redacted = redact_sensitive_text(text)

    assert "not-a-real-password" not in redacted
    assert "not-a-real-token" not in redacted
    assert redacted.count("<redacted>") == 2


def test_redacts_credentials_embedded_in_connection_urls():
    password = "-".join(["database", "test", "password"])  # noqa: FLY002
    scheme = "postgresql://"
    text = f"connection failed: {scheme}service:{password}@db:5432/app"

    redacted = redact_sensitive_text(text)

    assert password not in redacted
    expected = scheme + "service:<redacted>@db:5432/app"
    assert expected in redacted


def test_redacts_basic_auth_query_tokens_and_webhooks():
    secret = "-".join(["not", "a", "real", "secret"])  # noqa: FLY002
    text = (
        f"https://service:{secret}@example.test/path?access_token={secret} "
        f"https://hooks.slack.com/services/{secret}"
    )

    redacted = redact_sensitive_text(text)

    assert secret not in redacted
    assert redacted.count("<redacted>") == 3


def test_redacts_quoted_values_cookies_and_extended_query_names():
    secret = "-".join(["quoted", "credential", "value"])  # noqa: FLY002
    text = (
        f'{{"client_secret": "{secret} with spaces"}}\n'
        f"Cookie: session={secret}\n"
        f"https://example.test/callback?refresh_token={secret}"
    )

    redacted = redact_sensitive_text(text)

    assert secret not in redacted
    assert "with spaces" not in redacted
    assert redacted.count("<redacted>") == 3


def test_redacts_unlabelled_jwt_tokens():
    token = ".".join(  # noqa: FLY002
        ["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiJ1c2VyIn0", "signature-value"]
    )

    redacted = redact_sensitive_text(f"upstream returned {token}")

    assert token not in redacted
    assert "<redacted-jwt>" in redacted


def test_formatter_redacts_exception_text():
    formatter = SensitiveDataFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="OPENAI_API_KEY=not-a-real-key",
        args=(),
        exc_info=None,
    )

    rendered = formatter.format(record)

    assert "not-a-real-key" not in rendered
    assert "<redacted>" in rendered


def test_formatter_preserves_delegate_layout_while_redacting():
    delegate = logging.Formatter("delegated %(levelname)s %(message)s")
    formatter = SensitiveDataFormatter(delegate=delegate)
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="request?access_token=not-a-real-token",
        args=(),
        exc_info=None,
    )

    rendered = formatter.format(record)

    assert rendered.startswith("delegated ERROR ")
    assert "not-a-real-token" not in rendered


def test_public_error_message_never_accepts_exception_details():
    message = public_error_message("Chat request")

    assert message == "Chat request failed; see server logs for details"
