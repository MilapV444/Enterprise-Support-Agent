"""The mocked-model harness (NFR-21 / TQ-ADP-01: TQ-D1, TQ-D2): no real model or Jev call in CI.

- ScriptedJev: the TypeSafe System One endpoint as an httpx transport for the real JevClient, so the real
  parsing, the DecisionEngine's checks and every caller's fail-safe path run. Each request draws one
  behaviour: a valid answer to every question (random option, level and confidence), or one of the ways an
  answer goes wrong (an option that does not exist, a confidence outside [0, 1], a missing answer, the wrong
  answer type, a body that is not JSON, HTTP 400 / 429 / 500, or no connection at all).
- ScriptedModel: a completion function for the LLM fallback classifier and any other `complete(prompt)`
  hook, returning random well-formed JSON or one of its malformed variants (prose, a missing field, wrong
  types, values out of range), or with can_fail raising as a provider outage does.

Both are seeded by the caller's random.Random, so a failing seed replays exactly.
"""

import json

import httpx

from core.orchestrator.decisions import INTENTS, SEVERITY, DecisionEngine, JevClient

BROKEN = ("unknown_option", "bad_confidence", "missing_answer", "wrong_type", "not_json", "http_400",
          "http_429", "http_500", "unreachable")


def valid_answer(question, rng):
    """A raw answer in the API's shape for one question."""
    confidence = rng.choice([rng.random(), rng.uniform(0.85, 1.0), 0.5, 0.9, 1.0])
    criteria = question.get("criteria") or []
    if question["type"] == "choice":
        return {"type": "choice", "choice": rng.choice(list(criteria)), "confidence": confidence}
    if question["type"] == "score":
        weights = [rng.random() for _ in criteria]
        total = sum(weights)
        probabilities = {str(i): w / total for i, w in enumerate(weights)}
        return {"type": "score", "score": rng.uniform(0, len(criteria) - 1), "confidence": confidence,
                "probabilities": probabilities}
    return {"type": "noul", "noul": rng.random()}


def broken_answers(questions, how, rng):
    answers = {qid: valid_answer(q, rng) for qid, q in questions.items()}
    qid = rng.choice(list(questions))
    if how == "unknown_option":
        answers[qid] = {"type": "choice", "choice": "SOMETHING_ELSE", "confidence": 0.99}
    elif how == "bad_confidence":
        answers[qid] = {**answers[qid], "confidence": rng.choice([1.5, -0.2])}
        if answers[qid]["type"] == "noul":
            answers[qid]["noul"] = rng.choice([1.5, -0.2])
    elif how == "missing_answer":
        del answers[qid]
    elif how == "wrong_type":
        others = {"noul": {"type": "noul", "noul": 0.9},
                  "choice": {"type": "choice", "choice": "true", "confidence": 0.9},
                  "score": {"type": "score", "score": 1.0, "confidence": 0.9, "probabilities": {"1": 1.0}},
                  "mystery": {"type": "mystery"}}
        answers[qid] = rng.choice([a for kind, a in others.items() if kind != questions[qid]["type"]])
    return answers


class ScriptedJev:
    """httpx transport handler; `log` keeps (questions, behaviour) for every request."""

    def __init__(self, rng, broken_share=0.3, behaviours=None):
        self.rng, self.broken_share, self.behaviours, self.log = rng, broken_share, behaviours, []

    def behaviour(self):
        if self.behaviours:
            return self.rng.choice(self.behaviours)
        return self.rng.choice(BROKEN) if self.rng.random() < self.broken_share else "valid"

    def __call__(self, request):
        questions = json.loads(request.content)["questions"]
        how = self.behaviour()
        self.log.append((questions, how))
        if how == "unreachable":
            raise httpx.ConnectError("Jev is down", request=request)
        if how.startswith("http_"):
            return httpx.Response(int(how.removeprefix("http_")), json={"error": how})
        if how == "not_json":
            return httpx.Response(200, text="<html>gateway timeout</html>")
        answers = ({qid: valid_answer(q, self.rng) for qid, q in questions.items()} if how == "valid"
                   else broken_answers(questions, how, self.rng))
        return httpx.Response(200, json={"answers": answers, "model": "jev-test",
                                         "usage": {"input_tokens": 10, "output_tokens": 1}})

    @property
    def all_valid(self):
        """Whether every decision got a valid answer: a 429 the client retried (the next request asks the
        same questions, and the 429 was not itself the retry) does not count against it."""
        retried, effective = False, []
        for (questions, how), following in zip(self.log, [*self.log[1:], None], strict=True):
            retry = how == "http_429" and not retried and following is not None and following[0] == questions
            if not retry:
                effective.append(how)
            retried = retry
        return all(how == "valid" for how in effective)


def engine(jev):
    """The real DecisionEngine over the real JevClient, talking to a ScriptedJev."""
    return DecisionEngine(JevClient("test-key", transport=httpx.MockTransport(jev), backoff=0))


class ScriptedModel:
    """complete(prompt) -> str for the LLM fallback classifier; `calls` counts the prompts."""

    def __init__(self, rng, can_fail=False):
        self.rng, self.calls, self.can_fail = rng, 0, can_fail

    def __call__(self, prompt):
        self.calls += 1
        how = self.rng.choice(["valid", "valid", "prose", "missing", "wrong_types", "out_of_range",
                               *(["down"] if self.can_fail else [])])
        if how == "down":
            raise ConnectionError("the provider is down")
        if how == "prose":
            return "I think this is probably a billing question."
        reply = {"intent": self.rng.choice(list(INTENTS)), "severity": self.rng.randrange(len(SEVERITY)),
                 "missing_details": self.rng.random() < 0.3, "confidence": self.rng.random()}
        if how == "missing":
            reply.pop(self.rng.choice(list(reply)))
        if how == "wrong_types":
            reply[self.rng.choice(["severity", "confidence"])] = "high"
        if how == "out_of_range":
            reply[self.rng.choice(["severity", "confidence"])] = self.rng.choice([9, -1, 1.7])
        return json.dumps(reply)
