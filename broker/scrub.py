"""PII and credential pattern scrubbing for broker output."""
from __future__ import annotations

import os
import re
from typing import List, Pattern

# Compiled once; applied after per-tool secret scrubbing.
_PATTERNS: List[tuple[Pattern[str], str]] = [
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+\b", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"\bpassword\s*[:=]\s*\S+", re.IGNORECASE), "password=[REDACTED]"),
    (re.compile(r"\bapi[_-]?key\s*[:=]\s*\S+", re.IGNORECASE), "api_key=[REDACTED]"),
    (re.compile(r"\bsecret\s*[:=]\s*\S+", re.IGNORECASE), "secret=[REDACTED]"),
    (re.compile(r"\btoken\s*[:=]\s*\S+", re.IGNORECASE), "token=[REDACTED]"),
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL_REDACTED]",
    ),
    (
        re.compile(r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{10,}\b"),
        "[STRIPE_KEY_REDACTED]",
    ),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[GITHUB_TOKEN_REDACTED]"),
    (re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"), "[GITHUB_TOKEN_REDACTED]"),
]


def pii_scrub_enabled() -> bool:
    raw = os.environ.get("BROKER_SCRUB_PII", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def scrub_pii(text: str) -> str:
    if not text or not pii_scrub_enabled():
        return text
    out = text
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out


def scrub_all(text: str, secrets: List[str]) -> str:
    from policy import scrub_secrets

    return scrub_pii(scrub_secrets(text, secrets))
