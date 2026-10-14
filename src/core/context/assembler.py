"""Slot-budget context assembler (FR-3 / ADP-03; FR-41 / CR-ADP-02 CR-D6).

The window is split into five slots, in prompt order: system 15 % · profile 15 % · knowledge 35 % · dialogue
25 % · scratchpad 10 %. No slot ever exceeds its share; each over-full slot compacts on its own:

- system (instructions + tool definitions): never compacted; too big is a build error; the cached prefix.
- profile pins: verbatim; the least important are left out.
- knowledge passages: best-ranked first (top 5), compressed when they do not fit, dropped if still too big.
- dialogue: the newest turns verbatim (at most 6), then the rolling summary if room is left.
- scratchpad: the newest notes first.

Untrusted text (passages, user turns) is wrapped in spotlighting delimiters; delimiters, dialogue and pins are
never compressed (CR-D6).
"""

import json
import math
import re
from dataclasses import dataclass, field

WINDOW = 16_384
QUOTAS = {"system": 0.15, "profile": 0.15, "knowledge": 0.35, "dialogue": 0.25, "scratchpad": 0.10}
MAX_PASSAGES = 5  # top parent chunks
MAX_TURNS = 6
OPEN, CLOSE = "<<<DATA {}>>>", "<<<END DATA>>>"


class ContextOverflow(ValueError):
    pass


def approx_tokens(text):
    """Deliberate over-estimate (UTF-8 bytes / 3) so budgets hold for any tokenizer we use.

    ponytail: swap in the provider's exact count (e.g. Anthropic count_tokens) when budgets get tight.
    """
    return math.ceil(len(text.encode()) / 3)


def delimit(text, label):
    """Spotlight untrusted text; anything inside that looks like a delimiter is defused first."""
    return f"{OPEN.format(label)}\n{text.replace('<<<', '‹‹‹').replace('>>>', '›››')}\n{CLOSE}"


# Interim compressor for knowledge passages (LongLLMLingua needs its own model): drops filler words and
# markup, then whole sentences if still too long - sentences without a protected word (negation, number,
# link, money) go first, from the end.
FILLER = set("a an the of to in on at for with by from as is are was were be been being that which who "
             "this these those it its very really just also basically simply please kindly so then there "
             "here our your their we you they will would can could should may might".split())
NEGATIONS = set("not no never none nothing neither nor except unless without cannot can't don't doesn't "
                "isn't aren't won't mustn't shouldn't".split())
PROTECTED = re.compile(r"\d|https?://|[$€£¥%@]|<<<|>>>")


def protected(word):
    return word.lower().strip(".,;:!?()") in NEGATIONS or bool(PROTECTED.search(word))


def compress_passage(text, target_tokens, count=approx_tokens):
    words = [w if protected(w) else w.strip("*#`>_") for w in text.split()]
    words = [w for w in words if w and (protected(w) or w.lower().strip(".,;:!?()") not in FILLER)]
    compact = " ".join(words)
    sentences = re.split(r"(?<=[.!?])\s+", compact)
    while len(sentences) > 1 and count(" ".join(sentences)) > target_tokens:
        plain = [i for i, s in enumerate(sentences) if not any(protected(w) for w in s.split())]
        sentences.pop(plain[-1] if plain else -1)
    return " ".join(sentences)


@dataclass
class Assembled:
    segments: dict[str, str]                  # slot -> rendered text, in prompt order
    usage: dict[str, int]                     # slot -> tokens used
    budgets: dict[str, int]                   # slot -> tokens allowed
    turns: list[dict[str, str]] = field(default_factory=list)  # dialogue turns kept, oldest first
    left_out: dict[str, int] = field(default_factory=dict)     # slot -> items that did not fit

    def to_anthropic(self):
        """Messages API shape: the cached prefix first, then profile and knowledge, then the dialogue."""
        system = [{"type": "text", "text": self.segments["system"], "cache_control": {"type": "ephemeral"}}]
        system += [{"type": "text", "text": self.segments[slot]} for slot in ("profile", "knowledge")
                   if self.segments[slot]]
        messages = []
        if self.segments["summary"]:
            messages.append({"role": "user", "content": [{"type": "text", "text": self.segments["summary"]}]})
        for turn in self.turns:
            text = delimit(turn["content"], "user message") if turn["role"] == "user" else turn["content"]
            if messages and messages[-1]["role"] == turn["role"]:
                messages[-1]["content"].append({"type": "text", "text": text})
            else:
                messages.append({"role": turn["role"], "content": [{"type": "text", "text": text}]})
        if self.segments["scratchpad"]:
            note = {"type": "text", "text": self.segments["scratchpad"]}
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"].append(note)
            else:
                messages.append({"role": "user", "content": [note]})
        return {"system": system, "messages": messages}


def assemble(system, tools=(), pins=(), passages=(), turns=(), summary="", scratchpad=(), window=WINDOW,
             count=approx_tokens, compress=compress_passage):
    """pins: [{"text", "importance"}], passages: [{"text", "score", "source"?}], turns: [{"role", "content"}].

    Returns Assembled; raises ContextOverflow when the system prompt and tools exceed their slot.
    """
    budgets = {slot: int(window * share) for slot, share in QUOTAS.items()}
    left_out = {}

    def fill(slot, blocks, separator="\n\n"):
        """Take blocks in order while they fit; returns the rendered text."""
        taken = []
        for block in blocks:
            if count(separator.join([*taken, block])) <= budgets[slot]:
                taken.append(block)
            else:
                left_out[slot] = left_out.get(slot, 0) + 1
        return separator.join(taken)

    prefix = system + ("\n\nTools:\n" + json.dumps(list(tools), indent=1) if tools else "")
    if count(prefix) > budgets["system"]:
        raise ContextOverflow(
            f"system prompt and tools need {count(prefix)} tokens, budget {budgets['system']}")

    ranked_pins = sorted(pins, key=lambda pin: -pin["importance"])
    profile = fill("profile", [f"- {pin['text']}" for pin in ranked_pins], separator="\n")

    knowledge_blocks = []
    for rank, passage in enumerate(sorted(passages, key=lambda p: -p["score"])[:MAX_PASSAGES]):
        label = f"passage {rank + 1}" + (f" ({passage['source']})" if passage.get("source") else "")
        block = delimit(passage["text"], label)
        room = budgets["knowledge"] - count("\n\n".join(knowledge_blocks))
        if count(block) > room:  # does not fit verbatim: compress to the room left, delimiters excluded
            block = delimit(compress(passage["text"], room - count(delimit("", label))), label)
        knowledge_blocks.append(block)
    knowledge = fill("knowledge", knowledge_blocks)

    kept, used = [], 0
    for turn in list(turns)[::-1][:MAX_TURNS]:  # newest first, verbatim, contiguous
        cost = count(delimit(turn["content"], "user message") if turn["role"] == "user" else turn["content"])
        if used + cost > budgets["dialogue"]:
            break
        kept.insert(0, turn)
        used += cost
    left_out["dialogue"] = len(turns) - len(kept)
    summary_text = f"Earlier in this conversation: {summary}" if summary else ""
    if summary_text and used + count(summary_text) > budgets["dialogue"]:
        summary_text = ""

    notes = fill("scratchpad", list(scratchpad)[::-1], separator="\n")

    segments = {"system": prefix, "profile": profile, "knowledge": knowledge, "summary": summary_text,
                "scratchpad": notes}
    usage = {"system": count(prefix), "profile": count(profile), "knowledge": count(knowledge),
             "dialogue": used + (count(summary_text) if summary_text else 0), "scratchpad": count(notes)}
    over = {slot: tokens for slot, tokens in usage.items() if tokens > budgets[slot]}
    if over:
        raise ContextOverflow(f"slot budgets exceeded: {over}")  # a bug in the above, never expected
    return Assembled(segments, usage, budgets, kept, left_out)
