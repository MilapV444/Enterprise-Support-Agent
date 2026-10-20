"""Finding PII and turning it into global deterministic tokens (SG-ADP-02: SG-D4, SG-D5).

token = "<KIND_" + first 8 hex of HMAC-SHA256(PII_TOKEN_KEY, normalised value) + ">"; the same value gives the
same token in every tenant and every turn, so search and joins still work on masked text. The key is the
shared, never-rotated token key (DL-D8). Technical identifiers on the allow-list are never masked.

ponytail: regex recognizers (email, phone, SSN, card with Luhn) stand in for Presidio; names need NER.
"""

import hashlib
import hmac
import logging
import re

TOKEN = re.compile(r"<(?:EMAIL|PHONE|SSN|CARD)_[0-9a-f]{8}>")
RECOGNIZERS = [  # earlier kinds win where matches overlap
    ("SSN", re.compile(r"(?<!\d)\d{3}\s*-\s*\d{2}\s*-\s*\d{4}(?!\d)|(?<!\d)\d{3} \d{2} \d{4}(?!\d)")),
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("PHONE", re.compile(r"(?<![\w.])\+?\(?\d[\d ().-]{7,18}\d(?![\w.])")),
]
ALLOW = re.compile("|".join([  # SG-D5 technical allow-list: PII candidates inside these spans stay as-is
    r"\b[A-Z]{2,4}-\d{4,8}\b",                                   # INV-9821, BUG-8192
    r"\b[a-z0-9-]+-(?:service|daemon|api|worker|proxy)\b",         # auth-user-service
    r"\b(?:admin|root|system|daemon|operator)\b",                  # system accounts
    r"\b(?:vpc|subnet|sg|i|k8s-pod)-[\w-]+|\barn:aws[\w:/.-]*",    # cloud resource ids
    r"\b(?:ERR|E)[_-][\w-]+|\bSIG[A-Z]+\b|\bHTTP[ _-]?\d{3}\b",     # error enums
    r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?",                        # ISO dates and times
    r"\bv\d+(?:\.\d+){1,3}\b|\b\d{1,2}(?:\.\d{1,2}){1,3}\b",       # versions (not dotted phones)
]))


def luhn(digits):
    total = 0
    for index, digit in enumerate(int(d) for d in reversed(digits)):
        doubled = digit * 2 if index % 2 else digit
        total += doubled - 9 if doubled > 9 else doubled
    return total % 10 == 0


def normalise(kind, value):
    digits = re.sub(r"\D", "", value)
    if kind == "EMAIL":
        return value.strip().lower()
    if kind == "PHONE":
        return ("+" if value.strip().startswith("+") else "") + digits
    return digits


def plausible(kind, value):
    digits = re.sub(r"\D", "", value)
    if kind == "CARD":
        return 13 <= len(digits) <= 19 and luhn(digits)
    if kind == "PHONE":
        return 9 <= len(digits) <= 15
    return True


def find(text):
    """[(start, end, kind, value)] for every PII span, non-overlapping, left to right."""
    found = [(*m.span(), "TOKEN", m.group(0)) for m in TOKEN.finditer(text)]  # already masked: leave it
    found += [(*m.span(), "ALLOWED", m.group(0)) for m in ALLOW.finditer(text)]
    for kind, pattern in RECOGNIZERS:
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            start = match.start() + match.group(0).index(value)
            if not plausible(kind, value):
                continue
            if all(start >= end or start + len(value) <= begin for begin, end, _, _ in found):
                found.append((start, start + len(value), kind, value))
    return sorted(span for span in found if span[2] not in ("TOKEN", "ALLOWED"))


class Tokenizer:
    def __init__(self, key):
        self.key = key if isinstance(key, bytes) else key.encode()

    def token(self, kind, value):
        digest = hmac.new(self.key, normalise(kind, value).encode(), hashlib.sha256).hexdigest()
        return f"<{kind}_{digest[:8]}>"

    def mask(self, text):
        """(masked text, {token: (kind, raw value)})."""
        out, last, found = [], 0, {}
        for start, end, kind, value in find(text):
            token = self.token(kind, value)
            found[token] = (kind, value)
            out += [text[last:start], token]
            last = end
        return "".join(out + [text[last:]]), found


class RedactingFilter(logging.Filter):
    """Masks PII in every log record before any handler sees it (AC-14)."""

    def __init__(self, tokenizer):
        super().__init__()
        self.tokenizer = tokenizer

    def filter(self, record):
        record.msg, record.args = self.tokenizer.mask(record.getMessage())[0], ()
        return True
