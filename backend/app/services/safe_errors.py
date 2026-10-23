"""Redact credentials in diagnostics, including exception tracebacks and URLs."""
import logging
import re


def redact_diagnostic(value: str) -> str:
    from ..config import get_settings
    settings = get_settings()
    text = str(value)
    for name in type(settings).model_fields:
        secret = getattr(settings, name)
        if any(word in name for word in ['key', 'token', 'secret', 'password']) and isinstance(secret, str) and secret:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)([?&](?:key|token|api_key|access_token)=)[^&\s\"\']+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)(Bearer\s+)[\w.\-]+', r'\1[REDACTED]', text)
    text = re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact_diagnostic(super().format(record))
