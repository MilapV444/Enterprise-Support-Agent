"""
Generate LLD page for Component [10/15]: Reliability / Performance / Scale.

Materializes checkpoint.md §14 (loop step 11): boundary, the gateway path,
degraded modes per failure, latency budgets, one card per sub-component
(mechanic + status), the Known/Unknown failure grid with step-9 effects
(after §14.9a), and a decision-log summary.

Only the page `page:lld_reliability` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, est_h, write_page

PID = "page:lld_reliability"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "rp")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [10/15]: RELIABILITY / PERFORMANCE / SCALE\n"
        "Limits by tenant / user / conversation / tokens · Degrade, don't drop · Self-hosted fallback LLM · "
        "Jev fallback classifier · Incident mode · One active turn · Multi-AZ, no cross-region failover",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Requests at the gateway (Comp 1)\n"
                 "• Health + latency signals (Comp 10 alerts)\n"
                 "• Dependency failures: LLM, Jev, tools, stores, regions", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Allow / degrade / 429 → Comp 1\n"
                 "• Degraded-mode flags → Orchestration\n"
                 "• Runbooks, incidents → on-call · DR plans → Data (8)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Tool retries + per-system breakers (TA-D10)\n"
                   "• Alerting (10) · cost budgets (12)\n"
                   "• HITL staffing (13)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Gateway path ────────────────────────────────────────────────────
    y += h + 40
    ga_y = y
    hg = row(ga_y + 45, [
        ("g1", "① Rate limits (RP-D1, D14)\n• Tenant, user, conversation\n• Tokens / min from an exact\n  usage counter", "light-blue", False),
        ("g2", "② Over limit (RP-D2)\n• Knowledge-base-only answer\n  (generated, or snippets)\n• Hard ceiling → 429 + Retry-After", "orange", False),
        ("g3", "③ One active turn (RP-D3)\n• Includes approval waits\n• New messages rejected:\n  'still working on your last message'", "light-violet", False),
        ("g4", "④ Incident mode? (RP-D6)\n• Declared by on-call\n• Jev Noul: about the outage?\n• Yes → prepared status answer", "yellow", False),
        ("g5", "⑤ Run the turn (RP-D8)\n• First status ≤ 1 s\n• p95: FAQ 5 s · diagnostics 20 s\n  · multi-specialist 45 s", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("g1", "g2"), ("g2", "g3"), ("g3", "g4"), ("g4", "g5")]):
        connect(f"g{i}", s, t, color="green")
    ga_h = hg + 70
    pb.frame_behind("gate", "FLOW A · A TURN AT THE GATEWAY (Sarah @ acme-corp, Monday peak)",
                    START_X, ga_y, TOTAL_W, ga_h, "green")

    # ── Degraded modes ──────────────────────────────────────────────────
    y = ga_y + ga_h + 40
    dm_y = y
    hd_ = row(dm_y + 45, [
        ("d1", "LLM PROVIDER DOWN (RP-D4)\n• Self-hosted open-weights\n  model in the region\n• Both down → snippets", "light-red", False),
        ("d2", "JEV DOWN (RP-D5)\n• Fallback LLM classifier for\n  triage + delegation\n• Guards, tool gating: fail-safe", "light-red", False),
        ("d3", "BURST / HERD (RP-D6)\n• Coalesce identical reads\n• Incident mode\n• Retry budgets (RP-D13)", "orange", False),
        ("d4", "TOOL BREAKER OPEN (RP-D7)\n• Hold the request up to 24 h\n• Answer to the inbox on recovery\n• Then a human", "light-violet", False),
        ("d5", "ZONE / DATA LOSS (RP-D10, D11, D15)\n• Multi-AZ in each region\n• Point-in-time recovery\n• Monthly drill → warm standby\n• Region loss = downtime (accepted)", "light-blue", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=40)
    dm_h = hd_ + 70
    pb.frame_behind("degrade", "FLOWS B–F · DEGRADED MODES (keep answering, never cache account facts)",
                    START_X, dm_y, TOTAL_W, dm_h, "red")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = dm_y + dm_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "ERROR RECOVERY\n\n✔ D5 Jev fallback\n✔ D10 Multi-AZ\n✔ D11 PITR + drills\n✔ D15 Warm standby", "light-green", False),
        ("s2", "RETRY / FALLBACK\n\n✔ D4 Fallback LLM\n✔ D7 Hold up to 24 h\n✔ D13 Retry budgets", "light-green", False),
        ("s3", "LATENCY\n\n✔ D8 Budgets per route", "light-green", False),
        ("s4", "THROUGHPUT\n\n✔ D3 One active turn\n✔ D6 Coalescing +\n   incident mode", "light-green", False),
        ("s5", "RATE LIMITING\n\n✔ D1 Four scopes\n✔ D2 Degrade, then 429\n✔ D14 Exact counter", "light-green", False),
        ("s6", "SCALABILITY\n\n✔ D9 Autoscale +\n   pre-warmed\n✔ D12 Load + chaos", "light-green", False),
    ], "light-green")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hs + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT  ·  Jev: incident Noul (uses 4, 8)", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Dropped without 429 → FIXED (degrade, then 429 + Retry-After)\n"
              "• KK2 Cold starts trip breakers → MITIGATED (pre-warmed minimum)\n"
              "• KK3 Retries multiply across layers → FIXED (D13 budgets)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Cost: standby, pre-warm, regional GPUs → OWNED (Comp 12)\n"
              "• KU2 Fallback model / classifier accuracy → MITIGATED (EV baselines)\n"
              "• KU3 SSE connections at peak → MITIGATED (autoscale + load tests)",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Users expect 'we know about the outage' → FIXED (incident mode)\n"
              "• UK2 Contracts expect uptime / failover → OWNED, accepted",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Token limits on sampled estimates → FIXED (exact counter)\n"
              "• UU2 Degraded answers overreach → MITIGATED (snippets, checks)\n"
              "• UU3 Drills copy production data → MITIGATED (standby = production)\n"
              "• UU4 Herd on recovery → MITIGATED (coalescing, queue rate limits)",
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
        ("dl1", "CONFIRMED (15 decisions + 5 follow-ups, none open)\n"
                "✔ D1 four limit scopes · D2 degrade then 429 · D3 one active turn\n"
                "✔ D4 self-hosted fallback LLM · D5 Jev fallback classifier · D6 incident mode\n"
                "✔ D7 hold up to 24 h · D8 latency budgets · D9 autoscale + pre-warm\n"
                "✔ D10 multi-AZ · D11 PITR + drills · D12 load + chaos\n"
                "✔ D13 retry budgets · D14 exact usage counter · D15 warm standby", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 1: 'still working' UX, locked conversation during approval, incident banner\n"
                "Comp 8: per-region counter store; standby in the erasure fan-out\n"
                "Comp 9: fallback baselines · Comp 10: SLOs from budgets, incident declaration\n"
                "Comp 12: GPU / standby / pre-warm cost · Comp 13: requests held 24 h → human\n"
                "Comp 14: load + chaos tests in CI · Legal: no cross-region failover\n\n"
                "Full reasoning: checkpoint.md §14", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §14.6 – §14.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")

    return pb.records("LLD - [10] Reliability / Performance / Scale", "aC")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
