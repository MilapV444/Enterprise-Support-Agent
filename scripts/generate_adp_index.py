"""
Generate docs/decisions/adp_index.md: the Architectural Decision Points (ADPs) per component.

ADPs are defined in docs/decisions/adp_groups.yaml (≈5 per component); each one groups
decisions from the decision log in docs/decisions/checkpoint.md §3. Each ADP entry here is
the brief for one detailed design document. Re-run after editing either file.
"""

import os

from adp_registry import COMPONENTS, ROOT, load_groups

TARGET = os.path.join(ROOT, "docs", "decisions", "adp_index.md")


def cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


def main():
    groups = load_groups()
    titles = {g["id"]: g["title"] for v in groups.values() for g in v}
    n_adps = sum(len(v) for v in groups.values())
    n_dec = sum(len(g["members"]) for v in groups.values() for g in v)

    out = [
        "# Architectural Decision Points (ADPs) — Index",
        "",
        "> **Generated** by [`scripts/generate_adp_index.py`](../../scripts/generate_adp_index.py) from "
        "[`adp_groups.yaml`](./adp_groups.yaml) (the grouping) and the decision log in "
        "[`checkpoint.md`](./checkpoint.md) §3. Do not edit by hand.  ",
        "> **Visual:** each component's LLD page in [`architecture.tldr`](../../diagrams/architecture.tldr) "
        "ends with the same ADP cards.",
        "",
        f"**{n_adps} ADPs** cover all **{n_dec} logged decisions**. An ADP is one architectural concern and "
        "is meant to become **one detailed design document**. Each entry below gives the document's brief: "
        "the question it answers, the chosen design, the decisions it must cover (with their one-line choices), "
        "where the reasoning is, and which ADPs in other components it must stay consistent with.",
        "",
        "## Summary",
        "",
        "| Component | ADPs | Decisions | Reasoning |",
        "| :--- | :--- | ---: | :--- |",
    ]
    for prefix, (name, section, _) in COMPONENTS.items():
        items = groups[prefix]
        ids = "<br>".join(f"{g['id']} · {g['title']}" for g in items)
        out.append(f"| **{name}** | {ids} | {sum(len(g['members']) for g in items)} | checkpoint.md {section} |")
    out += [f"| **Total** | **{n_adps}** | **{n_dec}** | |", ""]

    for prefix, (name, section, page) in COMPONENTS.items():
        out += [f"## {name}", "", f"Reasoning: `checkpoint.md` {section} · Diagram: `{page}`", ""]
        for g in groups[prefix]:
            related = ", ".join(f"{r} ({titles[r]})" for r in g.get("related", [])) or "—"
            out += [
                f"### {g['id']} · {g['title']}",
                "",
                f"- **Question:** {g['question']}",
                f"- **Chosen design:** {g['decision']}",
                f"- **Related ADPs:** {related}",
                "",
                "| Decision | Title | Choice | Notes |",
                "| :--- | :--- | :--- | :--- |",
            ]
            for d in g["decisions"]:
                out.append(f"| **{d['id']}** | {cell(d['title'])} | {cell(d['decision'])} | {cell(d['note'])} |")
            out.append("")

    with open(TARGET, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))
    print(f"Wrote {n_adps} ADPs ({n_dec} decisions) to {TARGET}.")


if __name__ == "__main__":
    main()
