"""The fact write path, run when a case resolves (FR-17 / MS-ADP-03: MS-D5, MS-D12, MS-D15, MS-D16, MS-D17,
MS-D19).

1. Sources: the customer's own turns, plus allow-listed scalar fields of tool outputs (tool.field = value,
   short single tokens only). Agent replies, retrieved passages and free text in tool output never reach the
   extractor, so an instruction planted in a ticket body or a document cannot become a "fact".
2. Extraction: `extract(texts) -> [{"statement", "category", "importance", "future"}]`, a model over masked
   text.
3. Filters in code: plans, intentions and speculation are dropped (only what is true now is kept), and so are
   account facts (SLA, contract, billing, plan), which live in the CRM.
4. Subject: Jev must say the fact is about the customer themself (>= 0.80); colleagues and third parties are
   dropped, and so is everything when Jev cannot answer.
5. Reconcile: Jev chooses ADD, NOOP, UPDATE or DELETE against the 3 nearest active facts, both sides masked
   the same way. Below 0.50, or when Jev cannot answer: NOOP. UPDATE closes the old fact and adds the new
   one in one transaction; DELETE closes it.
"""

import re
from dataclasses import dataclass, field

from core.orchestrator.decisions import JevUnavailable, mask
from memory.facts.store import CATEGORIES

ALLOWED_TOOL_FIELDS = {  # tool -> structured fields that may become facts (MS-D16)
    "get_cluster": {"version", "orchestrator", "cloud_provider"},
    "get_environment": {"os", "runtime", "deployment_model"},
}
SCALAR = re.compile(r"^[\w.:/+-]{1,64}$")  # one short token: no spaces, so no sentences
FUTURE = re.compile(r"\b(?:will|won't|shall|going to|gonna|plan(?:s|ned|ning)? to|aim(?:s|ing)? to|"
                    r"intend(?:s|ing)? to|hope to|want to|considering|thinking about|might|maybe|perhaps|"
                    r"soon|next (?:week|month|quarter|year)|scheduled)\b", re.IGNORECASE)
ACCOUNT = re.compile(r"\b(?:sla|service level|support tier|silver|gold|platinum|contract|billing|invoice|"
                     r"balance|subscription|licen[cs]es?|seats?|pricing|plan tier|"
                     r"account (?:owner|manager))\b",
                     re.IGNORECASE)
SUBJECT_AT, RECONCILE_AT = 0.80, 0.50
IS_SUBJECT = {"type": "noul",
              "instructions": "Is this statement a property, preference or action of the customer themself, "
                              "rather than of a colleague, vendor or third party?"}
RECONCILE = "How does the candidate fact change what is already known about the customer?"
LETTERS = "ABC"


@dataclass
class Report:
    added: list[str] = field(default_factory=list)
    updated: list[tuple[str, str]] = field(default_factory=list)  # (old statement, new statement)
    deleted: list[str] = field(default_factory=list)
    dropped: dict[str, list[str]] = field(default_factory=dict)   # reason -> statements

    def drop(self, reason, statement):
        self.dropped.setdefault(reason, []).append(statement)


def sources(events, allowed=ALLOWED_TOOL_FIELDS):
    """What the extractor may read: customer turns and allow-listed scalar tool fields, nothing else."""
    texts = []
    for event in events:
        if event.get("role") == "user":
            texts.append(event["content"])
        elif event.get("role") == "tool":
            output = event.get("output") or {}
            for name in sorted(allowed.get(event.get("tool"), set()) & set(output)):
                value = output[name]
                if isinstance(value, bool | int | float) or (isinstance(value, str) and SCALAR.match(value)):
                    texts.append(f"{event['tool']}.{name} = {value}")
    return texts


class FactWriter:
    def __init__(self, store, engine, extract, embed, allowed=ALLOWED_TOOL_FIELDS):
        """store: FactStore; engine: DecisionEngine; extract(texts) -> candidates; embed(texts) -> vectors."""
        self.store, self.engine, self.extract, self.embed = store, engine, extract, embed
        self.allowed = allowed

    def _about_customer(self, statement):
        try:
            answer = self.engine.ask({"fact": mask(statement)}, {"subject": IS_SUBJECT})["subject"]
        except JevUnavailable:
            return False
        return answer.value is True and answer.confidence >= SUBJECT_AT

    def _reconcile(self, statement, neighbours):
        """("ADD" | "NOOP" | "UPDATE" | "DELETE", neighbour or None)."""
        if not neighbours:
            return "ADD", None
        options = {"ADD": "A new fact that none of the existing facts covers",
                   "NOOP": "Already known, or not worth keeping"}
        state = {"candidate": mask(statement)}
        for letter, fact in zip(LETTERS, neighbours, strict=False):
            state[f"existing_{letter.lower()}"] = mask(fact.statement)  # masked like the candidate
            options[f"UPDATE_{letter}"] = f"Replaces existing fact {letter} with the candidate"
            options[f"DELETE_{letter}"] = f"Existing fact {letter} is no longer true, with no replacement"
        question = {"type": "choice", "instructions": RECONCILE, "criteria": options}
        try:
            answer = self.engine.ask(state, {"reconcile": question})["reconcile"]
        except JevUnavailable:
            return "NOOP", None
        if answer.confidence < RECONCILE_AT:
            return "NOOP", None
        if answer.value in ("ADD", "NOOP"):
            return answer.value, None
        action, letter = answer.value.split("_")
        return action, neighbours[LETTERS.index(letter)]

    def run(self, tenant_id, principal_id, case_id, events):
        """Extract and commit this case's facts for the principal from the verified token context."""
        report = Report()
        texts = sources(events, self.allowed)
        if not texts:
            return report
        for candidate in self.extract(texts):
            statement = candidate.get("statement", "").strip()
            importance = candidate.get("importance")
            if candidate.get("future") or FUTURE.search(statement):
                report.drop("not true yet", statement)
            elif ACCOUNT.search(statement):
                report.drop("account fact: read from the CRM", statement)
            elif candidate.get("category") not in CATEGORIES or not (
                    isinstance(importance, int) and 1 <= importance <= 10) or not statement:
                report.drop("malformed", statement)
            elif not self._about_customer(statement):
                report.drop("not about the customer", statement)
            else:
                self._commit(tenant_id, principal_id, case_id, statement, candidate, report)
        return report

    def _commit(self, tenant_id, principal_id, case_id, statement, candidate, report):
        embedding = self.embed([statement])[0]
        action, target = self._reconcile(statement, self.store.nearest(tenant_id, principal_id, embedding))
        if action == "NOOP":
            report.drop("no change", statement)
        elif action == "DELETE":
            if self.store.close(tenant_id, principal_id, target.id):
                report.deleted.append(target.statement)
        else:
            replaces = target.id if action == "UPDATE" else None
            new_id = self.store.add(tenant_id, principal_id, statement, candidate["category"],
                                    candidate["importance"], embedding, case_id, replaces)
            if new_id and replaces:
                report.updated.append((target.statement, statement))
            elif new_id:
                report.added.append(statement)
