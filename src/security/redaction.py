"""Redact credentials before text reaches logs or user-facing error responses."""

from __future__ import annotations

import logging
import re

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_CREDENTIAL_URL = re.compile(
    r"(?i)\b((?:https?|ftp|amqps?|postgres(?:ql)?|neo4j|mongodb(?:\+srv)?|mysql|redis)"
    r"://[^:/@\s]+:)([^@/\s]+)(@)"
)
_QUERY_CREDENTIAL = re.compile(
    r"(?i)([?&][A-Z0-9_.-]*(?:api[_-]?key|access[_-]?key|token|password|passwd|"
    r"passphrase|secret|credential)[A-Z0-9_.-]*=)([^&#\s]+)"
)
_HEADER_CREDENTIAL = re.compile(
    r"(?im)\b((?:proxy-)?authorization|cookie|set-cookie|x-api-key|api-key)"
    r"([ \t]*:[ \t]*)([^\r\n]+)"
)
_AUTHORIZATION = re.compile(r"(?i)\b(Bearer|Basic)([ \t]+)([A-Za-z0-9._~+/=-]{8,})")
_NAMED_CREDENTIAL = re.compile(r"""(?ix)
    (
        ["']?
        [A-Z0-9_.-]*
        (?:API[_-]?KEY|ACCESS[_-]?KEY|TOKEN|PASSWORD|PASSWD|PASSPHRASE|SECRET|CREDENTIAL)
        [A-Z0-9_.-]*
        ["']?[ \t]*[:=][ \t]*
    )
    (
        "(?:\\.|[^"\\])*"
        |
        '(?:\\.|[^'\\])*'
        |
        [^\s,;&}]{4,}
    )
    """)
_KNOWN_TOKEN = re.compile(
    r"(?i)\b("
    r"gh[pousr]_|github_pat_|glpat-|sk[-_](?:live|test)?_?|rk_(?:live|test)_|"
    r"whsec_|xox[baprs]-|AIza|ya29\.|AKIA|ASIA|ls__|SG\.|npm_|pypi-|hf_|"
    r"shp(?:at|ss|ca|pa)_|dop_v1_|ddapi_"
    r")([A-Za-z0-9._~+/=-]{8,})"
)
_JWT_TOKEN = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")
_WEBHOOK_URL = re.compile(
    r"(?i)\b(https://(?:hooks\.slack\.com/services|discord(?:app)?\.com/api/webhooks)/)"
    r"[^\s\"'<>]+"
)


def redact_sensitive_text(value: object) -> str:
    """Return text with common credential forms replaced by a fixed marker."""
    text = str(value)
    text = _PRIVATE_KEY.sub("<redacted-private-key>", text)
    text = _WEBHOOK_URL.sub(r"\1<redacted>", text)
    text = _CREDENTIAL_URL.sub(r"\1<redacted>\3", text)
    text = _QUERY_CREDENTIAL.sub(r"\1<redacted>", text)
    text = _HEADER_CREDENTIAL.sub(r"\1\2<redacted>", text)
    text = _AUTHORIZATION.sub(r"\1\2<redacted>", text)
    text = _NAMED_CREDENTIAL.sub(r"\1<redacted>", text)
    text = _KNOWN_TOKEN.sub(r"\1<redacted>", text)
    return _JWT_TOKEN.sub("<redacted-jwt>", text)


def public_error_message(context: str = "Request") -> str:
    """Return a client-safe message that contains no exception details."""
    return f"{context} failed; see server logs for details"


class SensitiveDataFormatter(logging.Formatter):
    """Apply credential redaction to the complete formatted log record."""

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: str = "%",
        validate: bool = True,
        *,
        defaults: dict[str, object] | None = None,
        delegate: logging.Formatter | None = None,
    ) -> None:
        super().__init__(fmt, datefmt, style, validate, defaults=defaults)
        self.delegate = delegate

    def format(self, record: logging.LogRecord) -> str:
        formatted = self.delegate.format(record) if self.delegate else super().format(record)
        return redact_sensitive_text(formatted)


def install_sensitive_logging() -> None:
    """Wrap every configured logging handler with output redaction."""
    loggers: list[logging.Logger] = [logging.getLogger()]
    loggers.extend(
        logger
        for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    )

    seen_handlers: set[int] = set()
    for configured_logger in loggers:
        for handler in configured_logger.handlers:
            handler_id = id(handler)
            if handler_id in seen_handlers or isinstance(handler.formatter, SensitiveDataFormatter):
                continue
            seen_handlers.add(handler_id)
            handler.setFormatter(
                SensitiveDataFormatter(delegate=handler.formatter or logging.Formatter())
            )
