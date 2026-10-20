"""Risk scorers for input screening (SG-ADP-01 SG-D2): each maps text to (score 0..1, categories).

- llama_guard(): Llama Guard 3 on Ollama (v1: llama-guard3:1b). It answers "safe" or "unsafe" plus hazard
  codes, not a probability, so it scores 0.0 or 1.0.
- prompt_guard(): Meta Prompt Guard through the Hugging Face inference API; scores are the classifier's
  INJECTION / JAILBREAK probabilities. (Ollama cannot serve this classifier.)
- pattern_injection(): a local pattern scorer that stands in for Prompt Guard where no key or model is set up.

Generative decision models (Jev, chat LLMs) are deliberately not used to detect injection (ADP-05-Q4).
A scorer that cannot answer raises ScorerUnavailable; the pipeline then treats the input as REVIEW.
"""

import re

import httpx


class ScorerUnavailable(RuntimeError):
    pass


def llama_guard(base_url="http://127.0.0.1:11434", model="llama-guard3:1b", timeout=10.0, transport=None):
    http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def score(text):
        try:
            reply = http.post("/api/chat", json={"model": model, "stream": False,
                                                 "messages": [{"role": "user", "content": text}]})
            reply.raise_for_status()
            verdict = reply.json()["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ScorerUnavailable(f"llama guard: {error}") from error
        first, _, rest = verdict.partition("\n")
        if first.strip().lower() == "safe":
            return 0.0, []
        if first.strip().lower() == "unsafe":
            return 1.0, [code.strip() for code in rest.replace(",", "\n").split() if code.strip()]
        raise ScorerUnavailable(f"llama guard: unexpected verdict {verdict[:40]!r}")
    return score


def prompt_guard(api_token, model="meta-llama/Prompt-Guard-86M",
                 base_url="https://api-inference.huggingface.co", timeout=10.0, transport=None):
    http = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {api_token}"}, timeout=timeout,
                        transport=transport)

    def score(text):
        try:
            reply = http.post(f"/models/{model}", json={"inputs": text})
            reply.raise_for_status()
            labels = reply.json()
            labels = labels[0] if labels and isinstance(labels[0], list) else labels
            scores = {item["label"].upper(): float(item["score"]) for item in labels}
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as error:
            raise ScorerUnavailable(f"prompt guard: {error}") from error
        risky = {label: s for label, s in scores.items() if label in ("INJECTION", "JAILBREAK")}
        top = max(risky.values(), default=0.0)
        return top, [label for label, s in risky.items() if s == top and top > 0]
    return score


# ponytail: a pattern list is a stand-in, not a classifier; replace with Prompt Guard when a key exists.
PATTERNS = [
    (0.95, "override", r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|all|earlier|system)\b"
                       r".{0,20}\b(instructions?|prompts?|rules?|messages?)\b"),
    (0.9, "prompt-leak", r"\b(reveal|print|show|repeat|output)\b.{0,30}\b(system prompt|instructions|hidden "
                         r"prompt|initial prompt)\b"),
    (0.85, "fence-spoof", r"<<<|>>>|</?\s*(system|untrusted_evidence|tool_output|instructions?)\s*>"),
    (0.8, "persona-swap", r"\byou are now\b|\bact as (an? )?(admin|administrator|developer|root|dan)\b|"
                          r"\bdeveloper mode\b|\bjailbreak\b"),
    (0.5, "role-play", r"\b(pretend|role-?play|imagine you are)\b"),
    (0.45, "authority", r"\b(as (the|your) (admin|system|developer)|this is an? (official|system) (message|"
                        r"notice))\b"),
]
COMPILED = [(weight, label, re.compile(pattern, re.IGNORECASE | re.DOTALL))
            for weight, label, pattern in PATTERNS]


def pattern_injection(text):
    hits = [(weight, label) for weight, label, pattern in COMPILED if pattern.search(text)]
    return max((weight for weight, _ in hits), default=0.0), [label for _, label in hits]
