"""Best-effort redaction shared by tool and execution boundaries."""

import re
from typing import Any


def redact(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
                       "[REDACTED PRIVATE KEY]", value, flags=re.S)
        value = re.sub(r"(?i)(\bBearer\s+)\S+", r"\1[REDACTED]", value)
        # Conservative best effort for common key=value or JSON-style fields.
        value = re.sub(
            r'''(?im)(["']?(?:password|passwd|secret|token|api[_-]?key)["']?\s*[:=]\s*)([^\r\n]+)''',
            r"\1[REDACTED]", value,
        )
        return value
    if isinstance(value, dict):
        return {redact(key, secrets): ("[REDACTED]" if re.search(r"password|passwd|secret|token|api.?key", key, re.I)
                      else redact(item, secrets)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    return value

