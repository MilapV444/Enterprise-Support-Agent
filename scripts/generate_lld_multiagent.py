"""
Generate LLD page for Component [5/15]: Multi-Agent & Communication.

Materializes checkpoint.md §9 (loop step 11): boundary, Flow A (cross-domain
case), Flow B (parallel audit), Flow C (blocked specialist) with Flow D
(adding a specialist), one card per sub-component (mechanic + status), Jev
placements, the Known/Unknown failure grid with step-9 effects (after §9.9a),
and a decision-log summary.

Only the page `page:lld_multiagent` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, add_adp_section, est_h, write_page

PID = "page:lld_multiagent"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "ma")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [5/15]: MULTI-AGENT & COMMUNICATION\n"
        "Coordinator + specialists (Generalist, Billing, Technical, Account & Ops) · Jev delegation · "
        "Typed contracts · Low-risk writes direct, rest via coordinator · One voice · 2 steps each, 6 per turn",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Triage labels + confidence and case state from Orchestration (Comp 2)\n"
                 "• User, tier, on-behalf-of token (Comp 1)\n"
                 "• Tool shortlists + gate results (Comp 5)\n"
                 "• Passages (Comp 3) and memory (Comp 4) for task briefs", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Tasks → specialists · proposed writes → Tools (5) via coordinator\n"
                 "• One merged reply + actions → Orchestration, confidence gate (9)\n"
                 "• Blocked, low-confidence, numeric conflicts → HITL (13)\n"
                 "• Per-agent traces + tokens → Observability (10), Cost (12)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Triage + FSM (Comp 2) · tool execution + approval (5)\n"
                   "• Retrieval (3) · memory + checkpoints (4, MS-D8)\n"
                   "• Model per agent (12) · policy (7)\n"
                   "• Output checks on the reply (12)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Flow A: cross-domain case ───────────────────────────────────────
    y += h + 40
    fa_y = y
    r1_y = fa_y + 45
    h1 = row(r1_y, [
        ("a0", "NOT OWNED →\nTriage: technical + billing\n(Jev, ADP-05)", None, True),
        ("a1", "① Delegate (MA-D3)\n• Jev Choice: lead = Technical\n• Jev Noul: billing needed? yes\n• Low confidence → human", "yellow", False),
        ("a2", "② Brief (MA-D4, D5)\n• Typed task: goal, IDs, pinned constraints\n• Evidence references\n• Conversation readable on demand", "light-blue", False),
        ("a3", "③ Technical Specialist (D9)\n• Own identity; reads + low-risk writes\n• Monitoring + BUG-8192 (Knowledge)\n• Result: resync caused the traffic", "light-violet", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    r2_y = r1_y + h1 + 70
    h2 = row(r2_y, [
        ("a7", "⑦ One Reply (MA-D12, D17)\n• Only the coordinator speaks\n• One voice, shared persona\n• Jev check: redirects user? (D13)", "light-green", False),
        ("a6", "⑥ Merge (MA-D7, D15, D16)\n• Jev Score per claim vs. evidence\n• Numeric disagreement → human\n• Success only after Tools verifies (D14)", "orange", False),
        ("a5", "⑤ Proposed Write → Tools\n• Coordinator sends apply_credit_memo\n• Tier: ≥ $1,000 → human approval\n• (TA-D5, D6)", "light-red", False),
        ("a4", "④ Billing Specialist (D6: after ③)\n• Reads INV-9821 · adds a case note (low-risk)\n• Links $12,400 line to the resync\n• Credit is financial → proposed to coordinator", "light-violet", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    fa_h = (r2_y + h2 + 25) - fa_y
    pb.frame_behind("flowA", "FLOW A · CROSS-DOMAIN CASE (Sarah @ acme-corp: \"DB failed over after v4.2 upgrade … $12,400 overage\")",
                    START_X, fa_y, TOTAL_W, fa_h, "green")
    for i, (s, t) in enumerate([("a0", "a1"), ("a1", "a2"), ("a2", "a3")]):
        connect(f"a{i}", s, t, color="blue")
    connect("turn", "a3", "a4", fa="B", ta="T", color="grey", label="finding")
    for i, (s, t) in enumerate([("a4", "a5"), ("a5", "a6"), ("a6", "a7")]):
        connect(f"b{i}", s, t, fa="L", ta="R", color="green")

    # ── Flow B: parallel audit ──────────────────────────────────────────
    y = fa_y + fa_h + 40
    fb_y = y
    hb = row(fb_y + 45, [
        ("c1", "① Plan (MA-D6)\n• 3 independent subtasks\n• Run in parallel", "light-blue", False),
        ("c2", "② SLA terms\n• Knowledge retrieval (Comp 3)", "light-violet", False),
        ("c3", "③ Q2 EU uptime\n• Technical specialist", "light-violet", False),
        ("c4", "④ Credits applied\n• Billing specialist", "light-violet", False),
        ("c5", "⑤ Join (MA-D7, D16)\n• Numbers compared in code\n• Disagreement → human\n• Text claims: Jev Score", "orange", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("c1", "c2"), ("c2", "c3"), ("c3", "c4"), ("c4", "c5")]):
        connect(f"c{i}", s, t, color="violet")
    fb_h = hb + 70
    pb.frame_behind("flowB", "FLOW B · PARALLEL AUDIT (Scenario 7: EU uptime vs. SLA + credits) · ≤ 5 specialists, 2 steps each, 6 per turn (MA-D8)",
                    START_X, fb_y, TOTAL_W, fb_h, "violet")

    # ── Flow C + D ──────────────────────────────────────────────────────
    y = fb_y + fb_h + 40
    fc_y = y
    hc = row(fc_y + 45, [
        ("d1", "① Specialist blocked\n• Needs another domain's data\n• or hits its 2-step limit", "light-blue", False),
        ("d2", "② Typed 'blocked' result (D4)\n• Back to the coordinator\n• Never 'contact the other team'", "yellow", False),
        ("d3", "③ Re-plan once or escalate\n• Human gets every finding\n• (ADP-04 diagnostic packet)", "orange", False),
        ("d4", "ADDING A SPECIALIST (Flow D)\n• Static registry entry (D10)\n• Own identity; reads + low-risk writes (D9)\n• LangGraph subgraph, same checkpoint (D11)", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("d1", "d2"), ("d2", "d3")]):
        connect(f"d{i}", s, t, color="blue")
    fc_h = hc + 70
    pb.frame_behind("flowC", "FLOW C · BLOCKED SPECIALIST  +  FLOW D · ADDING A SPECIALIST",
                    START_X, fc_y, TOTAL_W, fc_h, "blue")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = fc_y + fc_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "SPECIALIZED AGENTS\nInstructions, tools, scope per specialist.\n\n✔ D2 Generalist, Billing, Technical,\n   Account & Ops\n✔ D9 Own identity; low-risk writes direct", "light-green", False),
        ("s2", "DELEGATION\nWhich specialist(s), and the task.\n\n✔ D3 Jev Choice + Noul per specialist\n✔ Low confidence → human", "light-green", False),
        ("s3", "AGENT COMMUNICATION\nFormat and context between agents.\n\n✔ D4 Typed contracts via coordinator\n✔ D5 Brief + on-demand reads\n✔ D14 Proposals only", "light-green", False),
        ("s4", "COORDINATION\nOrder, join, conflicts, limits, reply.\n\n✔ D1 Coordinator · D6 parallel if independent\n✔ D18 Parallel = read-only\n✔ D7 Jev claims · D16 numbers → human\n✔ D8 Depth 1, ≤ 5, 2 / 6 steps\n✔ D12 One voice · D13 redirect check\n✔ D15 One reply · D17 shared persona", "light-green", False),
        ("s5", "AGENT DISCOVERY\nRegistry of specialists.\n\n✔ D10 Static registry\n✔ D11 LangGraph subgraphs (upstream)", "light-green", False),
    ], "light-green")

    # ── Jev placements ──────────────────────────────────────────────────
    y += hs + 30
    hj = row(y, [
        ("jev", "JEV IN THIS COMPONENT (ADP-05, masked input only)\n"
                "• Delegation: Choice lead (incl. generalist) + Noul per specialist (D3) · uses 1, 4, 9\n"
                "• Conflicts: Score per claim vs. evidence (D7) · uses 6, 9\n"
                "• Reply check: Noul 'sends the user to another team?' (D13) · uses 2, 7\n"
                "• Step success: Noul (ADP-05-Q1) · uses 6, 9", "yellow", False),
        ("nojev", "NOT JEV\n"
                  "• Numeric comparisons (D16), budgets and step caps: code\n"
                  "• Briefs and the reply text: LLM", "light-red", False),
    ], "yellow")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hj + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Task missing a required field → FIXED (D4 typed contracts)\n"
              "• KK2 Delegation loops / runaway fan-out → FIXED (D8 depth 1, ≤ 5)\n"
              "• KK3 Specialist makes a risky write → MITIGATED (D9: low-risk only, reviewed class)\n"
              "• KK4 Turn runs out of steps → MITIGATED (2 / 6 steps, then human)\n"
              "• KK5 Wrong specialist → MITIGATED (low confidence → human)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Token cost of multi-agent turns → OWNED (Comp 12)\n"
              "• KU2 Jev claim-scoring accuracy → OWNED (Comp 9 tests)\n"
              "• KU3 Latency of parallel / chained specialists → OWNED\n"
              "• KU4 Briefs miss context → MITIGATED (on-demand reads, logged)",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Bureaucratic ping-pong → MITIGATED (one voice + Jev redirect check)\n"
              "• UK2 Inconsistent voices → FIXED (D12, D17)\n"
              "• UK3 Conflicting diagnoses → MITIGATED (Jev claims, tie → human)",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 'I've issued your credit' before it ran → FIXED (D14)\n"
              "• UU2 Parallel specialists contradict each other → FIXED (D15 one reply)\n"
              "• UU3 Injection via conversation reads → MITIGATED (low-risk writes only)\n"
              "• UU4 Jev misjudges numbers → FIXED (D16 → human)\n"
              "• UU5 No fitting specialist → MITIGATED ('generalist' option)\n"
              "• UU6 Several specialists write the same record → FIXED (D18 writes only when alone)",
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
        ("dl1", "CONFIRMED (18 decisions + follow-ups, none open)\n"
                "✔ D1 coordinator + specialists · D2 Generalist, Billing, Technical, Account & Ops\n"
                "✔ D3 Jev delegation · D4 typed contracts · D5 brief + reads\n"
                "✔ D6 parallel if independent · D7 Jev claims · D8 depth 1, ≤ 5, 2 / 6 steps\n"
                "✔ D9 own identity, low-risk writes direct · D10 static registry · D11 subgraphs (upstream)\n"
                "✔ D12 one voice (revised) · D13 redirect check · D14 proposals only\n"
                "✔ D15 one reply · D16 numbers → human · D17 shared persona\n"
                "✔ D18 writes only when a specialist runs alone", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 2: coordinator + specialist subgraphs; step caps beside ADP-04\n"
                "Comp 5: allow-lists per specialist (reads + low-risk writes); higher-risk writes via coordinator\n"
                "Comp 9: delegation + conflict tests · Comp 12: tokens + model per specialist\n"
                "Comp 13: low-confidence delegation, blocked results, numeric conflicts\n\n"
                "OWNED RISKS TO WATCH\n"
                "KU1 token cost · KU2 claim scoring · KU3 latency\n\n"
                "Full reasoning: checkpoint.md §9", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §9.6 – §9.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")


    # ── Architectural Decision Points (from the checkpoint.md decision log) ──
    add_adp_section(pb, "MA", START_X, TOTAL_W)

    return pb.records("LLD - [5] Multi-Agent & Communication", "a7")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
