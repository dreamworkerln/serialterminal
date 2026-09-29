from __future__ import annotations

import re
from typing import Any


BASE64_PLACEHOLDER = "<base64>"

_BINARY_COMMAND_RE = re.compile(
    r"(?m)(?P<prefix>^[ \t]*/bin[ \t]+)"
    r"(?P<payload>[A-Za-z0-9+/]+={0,2})(?=\r?$)"
)
_BINARY_PRESENTATION_RE = re.compile(
    r"(?m)(?P<prefix>\[BINARY\][ \t]+)"
    r"(?P<payload>[A-Za-z0-9+/]+={0,2})(?=\r?$)"
)
_JSON_B64_FIELD_RE = re.compile(
    r'(?P<prefix>"[^"]*_b64"\s*:\s*")(?P<payload>[^"]*)(?P<suffix>")'
)


def redact_base64_text(text: str) -> str:
    """Replace known base64 payload positions while preserving surrounding context."""
    value = _BINARY_COMMAND_RE.sub(
        lambda match: match.group("prefix") + BASE64_PLACEHOLDER,
        text,
    )
    value = _BINARY_PRESENTATION_RE.sub(
        lambda match: match.group("prefix") + BASE64_PLACEHOLDER,
        value,
    )
    return _JSON_B64_FIELD_RE.sub(
        lambda match: (
            match.group("prefix")
            + BASE64_PLACEHOLDER
            + match.group("suffix")
        ),
        value,
    )


def redact_base64_payload(value: Any) -> Any:
    """Return a logging-safe copy with *_b64 fields and known text payloads redacted."""
    if isinstance(value, dict):
        return {
            key: (
                BASE64_PLACEHOLDER
                if isinstance(key, str)
                and key.endswith("_b64")
                and isinstance(item, str)
                else redact_base64_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_base64_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_base64_payload(item) for item in value)
    if isinstance(value, str):
        return redact_base64_text(value)
    return value
