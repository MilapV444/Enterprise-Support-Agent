"""
Generate LLD page for Component [14/15]: Deployment & LLMOps.

Materializes checkpoint.md §18 (loop step 11): boundary, environments, the
two release tracks (code vs. behaviour / models), versioning, secrets and
in-flight workflows, one card per sub-component (mechanic + status), the
Known/Unknown failure grid with step-9 effects (after §18.9a), and a
decision-log summary.

Only the page `page:lld_deployment` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, est_h, write_page

PID = "page:lld_deployment"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "dl")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [14/15]: DEPLOYMENT & LLMOPS\n"
        "Code ships continuously · Behaviour + model changes ship on a schedule through the gate and a canary · "
        "LLMs on latest, embedding + Jev pinned · Continue-As-New · Kubernetes per region",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Merge + release verdicts (Comp 13, 9)\n"
                 "• Infrastructure needs from every component\n"
                 "• SLO health (Comp 10)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Running releases per region\n"
                 "• Deploy / rollback events → Observability (10)\n"
                 "• Release records → audit (8) · secrets → services", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• What the gate requires (EV-D5) · tests (13)\n"
                   "• Alerting (10) · capacity (11)\n"
                   "• Tenant settings content (DP-D12)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Environments ────────────────────────────────────────────────────
    y += h + 40
    en_y = y
    he = row(en_y + 45, [
        ("e1", "DEV\n• Per developer / shared", "light-blue", False),
        ("e2", "STAGING (US only, DL-D1)\n• Fakes + recordings (EV-D4)\n• US tenants' samples only (DL-D12)", "orange", False),
        ("e3", "PRODUCTION US\n• Kubernetes + Helm (DL-D9)\n• GPU serving for self-hosted tier", "light-green", False),
        ("e4", "PRODUCTION EU\n• Same stack, own stores\n• EU issues seen first here (KU2)", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=40)
    en_h = he + 70
    pb.frame_behind("env", "ENVIRONMENTS (DL-D1, D9, D12)",
                    START_X, en_y, TOTAL_W, en_h, "blue")

    # ── Two release tracks ──────────────────────────────────────────────
    y = en_y + en_h + 40
    tr_y = y
    r1_y = tr_y + 45
    h1 = row(r1_y, [
        ("c1", "CODE TRACK ①\n• Merge passes the merge gate\n  (TQ-D9)", "light-blue", False),
        ("c2", "② CI path rule (DL-Q3)\n• Touches prompts, Jev questions,\n  thresholds, policies, model config?\n  → held for the behaviour track", "yellow", False),
        ("c3", "③ Deploy at once (DL-D4)\n• All at once per region\n• Continue-As-New for workflows\n  (DL-D6), signals drained first", "light-violet", False),
        ("c4", "④ Rollback (DL-D5)\n• Manual redeploy of the\n  previous version", "light-red", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    r2_y = r1_y + h1 + 50
    h2 = row(r2_y, [
        ("b1", "BEHAVIOUR / MODEL TRACK ①\n• Scheduled release (DL-D10)\n• Full gate (EV-D5, CR-D12)", "orange", False),
        ("b2", "② Shadow (EV-D12)\n• Live input, writes recorded only", "light-violet", False),
        ("b3", "③ Canary (EV-D7, DL-Q2)\n• Read-only routes\n• Evidence only for routes covered", "light-violet", False),
        ("b4", "④ All at once\n• Thresholds recalibrated (EV-D9)", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("c1", "c2"), ("c2", "c3"), ("c3", "c4")]):
        connect(f"c{i}", s, t, color="blue")
    for i, (s, t) in enumerate([("b1", "b2"), ("b2", "b3"), ("b3", "b4")]):
        connect(f"b{i}", s, t, color="orange")
    connect("held", "c2", "b1", fa="B", ta="T", color="grey", label="held")
    tr_h = (r2_y + h2 + 25) - tr_y
    pb.frame_behind("tracks", "FLOW A · TWO RELEASE TRACKS",
                    START_X, tr_y, TOTAL_W, tr_h, "green")

    # ── Versions + secrets ──────────────────────────────────────────────
    y = tr_y + tr_h + 40
    vs_y = y
    hv = row(vs_y + 45, [
        ("v1", "MODELS (DL-D3, Flow C)\n• LLM tiers: providers' latest\n• Embedding model: pinned\n• Jev version: pinned", "yellow", False),
        ("v2", "INDEX (DL-D11, Flow D)\n• Embedding change → re-index\n  in place, maintenance window", "light-blue", False),
        ("v3", "WORKFLOWS (DL-D6, Flow B)\n• Continue-As-New at release\n• LangGraph checkpoints migrated\n  (MS-D13, tested TQ-D14)", "light-violet", False),
        ("v4", "SECRETS (DL-D7, D8, Flow E)\n• Secrets manager per region\n• Scheduled rotation\n• Token key in each region, not rotated", "light-red", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=40)
    vs_h = hv + 70
    pb.frame_behind("ver", "FLOWS B–E · VERSIONS, INDEX, IN-FLIGHT WORKFLOWS, SECRETS",
                    START_X, vs_y, TOTAL_W, vs_h, "violet")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = vs_y + vs_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS  ·  No Jev use (version pinned; outage fallback RP-D5)", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "ENVIRONMENTS\n\n✔ D1 One US staging\n✔ D12 US samples only", "light-green", False),
        ("s2", "CI/CD\n\n✔ D9 Kubernetes + IaC\n✔ D10 Two tracks", "light-green", False),
        ("s3", "VERSIONING\n\n✔ D2 With code + path rule\n✔ D3 Latest LLMs, pinned\n   embedding + Jev\n✔ D6 Continue-As-New\n✔ D11 Re-index in place", "light-green", False),
        ("s4", "CONFIG / SECRETS\n\n✔ D7 Rotated secrets\n✔ D8 Token key per region", "light-green", False),
        ("s5", "DEPLOY / ROLLBACK\n\n✔ D4 Code at once;\n   behaviour canaried\n✔ D5 Manual rollback", "light-green", False),
    ], "light-green")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hs + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Bad release hits a whole region → MITIGATED (behaviour canaried)\n"
              "• KK2 Leaked / stale secret → MITIGATED (rotation)\n"
              "• KK3 Workflow change breaks in-flight runs → MITIGATED (Continue-As-New)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Re-index window impact → OWNED\n"
              "• KU2 EU-only issues first seen in production → OWNED, accepted",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 LLM tiers change without notice → OWNED, accepted",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Silent model changes → MITIGATED (embedding + Jev pinned)\n"
              "• UU2 EU samples in US staging → FIXED (D12)\n"
              "• UU3 Signals lost during Continue-As-New → MITIGATED (drain first)\n"
              "• UU4 Ungated behaviour changes → FIXED (CI path rule)\n"
              "• UU5 Token key exposure → OWNED, accepted",
    }
    half = (TOTAL_W - GAP) / 2
    top_h = max(est_h(q["q1"], half), est_h(q["q2"], half))
    bot_h = max(est_h(q["q3"], half), est_h(q["q4"], half))
    add("q1", q["q1"], START_X, y, half, top_h, "light-blue")
    add("q2", q["q2"], START_X + half + GAP, y, half, top_h, "orange")
    add("q3", q["q3"], START_X, y + top_h + GAP, half, bot_h, "light-violet")
    add("q4", q["q4"], START_X + half + GAP, y + top_h + GAP, half, bot_h, "light-red")

    # ── Decision log summary ────────────────────────────────────────────
    y += top_h + GAP + bot_h + 40
    dl_y = y
    y += 40
    hd = row(y, [
        ("dl1", "CONFIRMED (12 decisions + 3 follow-ups, none open)\n"
                "✔ D1 one US staging · D2 behaviour with code + path rule\n"
                "✔ D3 latest LLMs, embedding + Jev pinned · D4 code at once, behaviour canaried\n"
                "✔ D5 manual rollback · D6 Continue-As-New · D7 rotated secrets\n"
                "✔ D8 token key per region · D9 Kubernetes · D10 two tracks\n"
                "✔ D11 re-index in place · D12 US samples only in staging", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 1: change notices for behaviour releases\n"
                "Comp 9: canary evidence, recalibration on Jev upgrades\n"
                "Comp 10: deploy / rollback events · Comp 11: rollback runbook\n"
                "Comp 13: Continue-As-New + signal-drain tests\n\n"
                "Full reasoning: checkpoint.md §18", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §18.6 – §18.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")

    return pb.records("LLD - [14] Deployment & LLMOps", "aG")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
