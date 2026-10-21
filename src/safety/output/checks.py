"""Output checks on every reply before delivery (FR-32 / SG-ADP-03: SG-D6, SG-D15). No model, no tone check.

1. Leakage: known credential formats or long high-entropy strings, or a 12-word run copied from the system
   prompt or from an internal-only passage -> the reply is blocked. Raw personal data in a draft (drafts only
   carry tokens) is redacted.
2. URLs and markdown: raw HTML, spotlight fences and images are removed; a link survives only as HTTPS to an
   allow-listed domain that is not a private address, otherwise only its text remains.
3. Promises: refund / guarantee / waiver / price / legal commitments need a verified executed action of that
   kind, or must say the action is pending; an unbacked one holds the reply for exactly one rewrite, and a
   second failure goes to a human.
"""

import ipaddress
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlparse

from safety.pii.tokens import find as find_pii

CREDENTIALS = re.compile(
    r"\b(?:sk_(?:live|test)_[0-9a-zA-Z]{16,}|sk-ant-[\w-]{20,}|AKIA[0-9A-Z]{16}|ghp_[0-9a-zA-Z]{36}|"
    r"xox[abposr]-[\w-]{10,}|eyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
CANDIDATE = re.compile(r"[A-Za-z0-9_\-+/=]{24,}")
NGRAM = 12
# Tags and spotlight fences; PII tokens like <EMAIL_x> do not match, so they survive.
HTML = re.compile(r"</?[a-zA-Z][a-zA-Z0-9-]*(?:\s[^<>]*)?/?>|<<<[^>]*>>>")
IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BARE_URL = re.compile(r"\bhttps?://[^\s<>()\[\]]+")
PROMISES = {
    "refund": r"\b(we|i)('ll| will| shall) (issue a )?refund|\bwill be (refunded|credited)|\brefund you\b|"
              r"\bcredit (to )?your account\b",
    "guarantee": r"\bguarantee[sd]?\b|\b(we|i) promise\b",
    "waiver": r"\bwaive[sd]?\b|\bat no (extra )?(cost|charge)\b|\bfree of charge\b",
    "price": r"\bwill (only )?cost\b|\bprice will be\b|\bdiscount of\b",
    "legal": r"\b(legally|contractually)\b|\bwe are liable\b|\bcompensat(e|ion)\b",
}
PENDING = re.compile(r"\b(pending|awaiting|requires? (formal )?(approval|authori[sz]ation)|once approved|"
                     r"if approved|subject to (approval|review))\b", re.IGNORECASE)


def entropy(text):
    counts = Counter(text)
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def shared_run(reply, source, n=NGRAM):
    """True when the reply copies n consecutive words of the source."""
    source_words = words(source)
    grams = {tuple(source_words[i:i + n]) for i in range(len(source_words) - n + 1)}
    reply_words = words(reply)
    return any(tuple(reply_words[i:i + n]) in grams for i in range(len(reply_words) - n + 1))


def safe_url(url, allowed_domains):
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        return False
    try:
        if not ipaddress.ip_address(host).is_global:
            return False
    except ValueError:
        pass
    return any(host == domain or host.endswith("." + domain) for domain in allowed_domains)


def sanitise(text, allowed_domains):
    text = IMAGE.sub(lambda m: m.group(1), text)
    text = HTML.sub("", text)
    text = LINK.sub(lambda m: m.group(0) if safe_url(m.group(2), allowed_domains) else m.group(1), text)
    def bare(match):
        url = match.group(0).rstrip(".,;:!?")  # sentence punctuation is not part of the URL
        kept = url if safe_url(url, allowed_domains) else "[link removed]"
        return kept + match.group(0)[len(url):]
    return BARE_URL.sub(bare, text)


def unbacked(text, verified_actions):
    """Claim types the reply commits to without an executed action of that type or a 'pending' wording."""
    done = {action["type"] for action in verified_actions if action.get("status") == "executed"}
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if PENDING.search(sentence):
            continue
        found += [kind for kind, pattern in PROMISES.items()
                  if kind not in done and re.search(pattern, sentence, re.IGNORECASE)]
    return sorted(set(found))


@dataclass
class Check:
    verdict: str                  # "deliver", "rewrite", "block" or "escalate"
    text: str                     # sanitised reply ("" when blocked)
    findings: list[str] = field(default_factory=list)
    rewrite_instruction: str | None = None


def check(draft, *, system_prompt="", internal_passages=(), allowed_domains=(), verified_actions=(),
          attempt=1):
    """Check one draft. attempt=2 is the draft after the single allowed rewrite."""
    leaks = [f"credential: {m.group(0)[:6]}..." for m in CREDENTIALS.finditer(draft)]
    leaks += [f"high-entropy string: {m.group(0)[:6]}..." for m in CANDIDATE.finditer(draft)
              if entropy(m.group(0)) >= 4.5 and not CREDENTIALS.search(m.group(0))]
    if system_prompt and shared_run(draft, system_prompt):
        leaks.append("system prompt text")
    if any(shared_run(draft, passage) for passage in internal_passages):
        leaks.append("internal-only passage text")
    if leaks:
        return Check("block", "", leaks)

    text = sanitise(draft, allowed_domains)
    findings = []
    for start, end, kind, _ in reversed(find_pii(text)):
        text = text[:start] + "[removed]" + text[end:]
        findings.append(f"raw {kind.lower()} redacted")
    claims = unbacked(text, verified_actions)
    if not claims:
        return Check("deliver", text, findings)
    findings += [f"unbacked {claim} commitment" for claim in claims]
    if attempt >= 2:
        return Check("escalate", text, findings)
    instruction = (f"Your reply makes a commitment that has not been carried out ({', '.join(claims)}). "
                   "Rephrase so it says the action is pending review or needs approval; do not promise it.")
    return Check("rewrite", text, findings, instruction)


def finalise(draft, rewrite, **context):
    """Check a draft; on an unbacked promise ask rewrite(instruction) once, then check the new draft."""
    first = check(draft, **context)
    if first.verdict != "rewrite":
        return first
    return check(rewrite(first.rewrite_instruction), attempt=2, **context)
