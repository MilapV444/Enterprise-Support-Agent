"""
Architectural Decision Points (ADPs) per component, read from the decision log.

Source of truth: docs/decisions/checkpoint.md §3 "Genesis Architectural Checkpoint Log".
Orchestration's ADPs are ADP-01 – ADP-05; every other component's ADPs are its
confirmed decisions (prefix-Dn, plus UA-Q2 / UA-Q3, which were logged as decisions).

Used by the LLD page generators (ADP card section) and generate_adp_index.py.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKPOINT = os.path.join(ROOT, "docs", "decisions", "checkpoint.md")

# prefix -> (component name, checkpoint section, LLD page name)
COMPONENTS = {
    "ADP": ("Agent Orchestration Core & Runtime", "§2", "LLD - Agent Orchestration & Planning Core"),
    "UA": ("[1] User & Application", "§5", "LLD - [1] User & Application"),
    "KR": ("[2] Knowledge & Retrieval", "§6", "LLD - [2] Knowledge & Retrieval"),
    "MS": ("[3] Memory & State", "§7", "LLD - [3] Memory & State"),
    "TA": ("[4] Tools & Actions", "§8", "LLD - [4] Tools & Actions"),
    "MA": ("[5] Multi-Agent & Communication", "§9", "LLD - [5] Multi-Agent & Communication"),
    "SG": ("[6] Safety, Security & Governance", "§10", "LLD - [6] Safety, Security & Governance"),
    "DP": ("[7] Data & Persistence", "§11", "LLD - [7] Data & Persistence"),
    "EV": ("[8] Evaluation & Experimentation", "§12", "LLD - [8] Evaluation & Experimentation"),
    "OB": ("[9] Observability & Monitoring", "§13", "LLD - [9] Observability & Monitoring"),
    "RP": ("[10] Reliability / Performance / Scale", "§14", "LLD - [10] Reliability / Performance / Scale"),
    "CR": ("[11] Cost & Resource Management", "§15", "LLD - [11] Cost & Resource Management"),
    "HL": ("[12] Human-in-the-Loop", "§16", "LLD - [12] Human-in-the-Loop"),
    "TQ": ("[13] Testing & Quality", "§17", "LLD - [13] Testing & Quality"),
    "DL": ("[14] Deployment & LLMOps", "§18", "LLD - [14] Deployment & LLMOps"),
    "CI": ("[15] Continuous Improvement", "§19", "LLD - [15] Continuous Improvement"),
}


GROUPS = os.path.join(ROOT, "docs", "decisions", "adp_groups.yaml")


def load_groups(path=GROUPS, validate=True):
    """Return {prefix: [ADP group dict, ...]} from adp_groups.yaml, each with resolved `decisions`.

    Validation: every logged decision is in exactly one group, members exist, related IDs exist,
    and each component has 4–6 groups (Orchestration: exactly its ADP-01 – ADP-05).
    """
    import yaml

    with open(path, encoding="utf-8") as f:
        groups = yaml.safe_load(f)
    log = load_adps()
    by_id = {a["id"]: a for v in log.values() for a in v}
    all_group_ids = {g["id"] for v in groups.values() for g in v}
    errors = []
    seen = {}
    for prefix, items in groups.items():
        if prefix not in COMPONENTS:
            errors.append(f"unknown component prefix {prefix}")
        if prefix != "ADP" and not 4 <= len(items) <= 6:
            errors.append(f"{prefix}: {len(items)} ADPs (expected 4–6)")
        for g in items:
            for m in g["members"]:
                if m not in by_id:
                    errors.append(f"{g['id']}: unknown member {m}")
                elif m in seen:
                    errors.append(f"{m} is in both {seen[m]} and {g['id']}")
                else:
                    seen[m] = g["id"]
            for r in g.get("related", []):
                if r not in all_group_ids:
                    errors.append(f"{g['id']}: unknown related ADP {r}")
            g["decisions"] = [by_id[m] for m in g["members"] if m in by_id]
    missing = sorted(set(by_id) - set(seen))
    if missing:
        errors.append(f"decisions not in any ADP: {missing}")
    if validate and errors:
        raise ValueError("adp_groups.yaml is inconsistent:\n  " + "\n  ".join(errors))
    return groups


def _clean(text):
    """Strip markdown emphasis / code marks and escaped pipes for plain-text display."""
    text = text.replace("\\|", "|")
    text = re.sub(r"\*\*|`", "", text)
    return text.strip()


def _sort_key(adp_id):
    kind, num = re.match(r"[A-Z]+-([A-Z]*)(\d+)", adp_id).groups()
    return ({"": 0, "D": 0, "Q": 1}.get(kind, 2), int(num))


def load_adps(path=CHECKPOINT):
    """Return {prefix: [dict(id, title, decision, note, date, status), ...]} in ID order."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    start = text.index("## 3. Genesis Architectural Checkpoint Log")
    end = text.index("\n## 4.", start)
    out = {}
    for line in text[start:end].splitlines():
        if not line.startswith("| **"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        adp_id = cells[0].strip("*")
        prefix = adp_id.split("-")[0]
        out.setdefault(prefix, []).append({
            "id": adp_id,
            "title": _clean(cells[2]),
            "decision": _clean(cells[3]),
            "note": _clean(" | ".join(cells[4:-2])),
            "date": cells[-2],
            "status": _clean(cells[-1]),
        })
    for prefix in out:
        out[prefix].sort(key=lambda a: _sort_key(a["id"]))
    return out
