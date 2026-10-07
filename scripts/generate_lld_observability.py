"""
Generate LLD page for Component [9/15]: Observability & Monitoring.

Materializes checkpoint.md §13 (loop step 11): boundary, the telemetry
pipeline per region, Flow A (Sarah's turn) with Flows B–E, one card per
sub-component (mechanic + status), the alert list, the Known/Unknown failure
grid with step-9 effects (after §13.9a), and a decision-log summary.

Only the page `page:lld_observability` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, add_adp_section, est_h, write_page

PID = "page:lld_observability"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "ob")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [9/15]: OBSERVABILITY & MONITORING\n"
        "OpenTelemetry · PII scrubbed in the collector · Tail sampling · Jaeger + OpenSearch per region · "
        "7 days · Internal SLOs for alerts · Costs estimated from kept traces · Jev failure categories",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Spans, logs, metrics from every component\n"
                 "• Temporal workflow state · Jev answers + confidence (ADP-05)\n"
                 "• Signals other loops asked for · erasure requests (DP-D13)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Dashboards + alerts → on-call (Comp 11)\n"
                 "• Traces + live signals → Evaluation (EV-D8)\n"
                 "• Failure reports → Improvement (16) · usage → Cost (12)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Decision records + audit (SG-D13, DP-D3) · scoring (9)\n"
                   "• Budgets (12) · incident response + failover (11)\n"
                   "• HITL queues (13) · fixing failures (16)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Pipeline ────────────────────────────────────────────────────────
    y += h + 40
    pl_y = y
    hp = row(pl_y + 45, [
        ("p1", "① Instrument (OB-D1)\n• OpenTelemetry in every service\n• LLM SDK spans for agent steps,\n  exported as OpenTelemetry", "light-blue", False),
        ("p2", "② Scrub (OB-D14)\n• Collector runs the PII\n  recognizers on spans + logs", "light-red", False),
        ("p3", "③ Tail sampling (OB-D4)\n• Keep errors, escalations,\n  risk-tier, slow traces\n• Sample the rest", "orange", False),
        ("p4", "④ Store per region (OB-D2, D12)\n• Jaeger + OpenSearch (traces)\n• JSON logs, trace ID per line\n• 7 days (OB-D5)", "light-violet", False),
        ("p5", "⑤ Use\n• Dashboards + alerts (OB-D7, D8)\n• Costs estimated (OB-D13)\n• Failure categories (OB-D11)", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("p1", "p2"), ("p2", "p3"), ("p3", "p4"), ("p4", "p5")]):
        connect(f"p{i}", s, t, color="blue")
    pl_h = hp + 70
    pb.frame_behind("pipe", "TELEMETRY PIPELINE · ONE PER REGION (US, EU)",
                    START_X, pl_y, TOTAL_W, pl_h, "blue")

    # ── Flows ───────────────────────────────────────────────────────────
    y = pl_y + pl_h + 40
    fa_y = y
    ha = row(fa_y + 45, [
        ("a1", "SARAH'S TURN (Flow A)\n• One trace: screening, Jev triage\n  + confidence, specialists, tools\n• Kept in full: has an escalation", "light-blue", False),
        ("a2", "BILLING DEGRADES (Flow B)\n• Breaker opens (TA-D10)\n• Breaker + burn-rate alerts\n• Affected cases: Temporal UI", "orange", False),
        ("a3", "COST SPIKE (Flow C)\n• Burst of identical questions\n• Per tenant / component\n  (estimated from kept traces)", "yellow", False),
        ("a4", "FAILED CONVERSATION (Flow D)\n• Rules on error codes + decisions\n• Else Jev Choice: failure category\n• → Comp 16, Comp 9", "light-violet", False),
        ("a5", "ERASURE (Flow E)\n• DP-D13 workflow deletes Sarah's\n  traces + logs by ID (OpenSearch)\n• Rest expires in 7 days", "light-red", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=40)
    fa_h = ha + 70
    pb.frame_behind("flows", "FLOWS A–E",
                    START_X, fa_y, TOTAL_W, fa_h, "green")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = fa_y + fa_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "LOGS\n\n✔ D12 JSON + trace ID\n✔ D5 7 days · D6 erasure\n✔ D14 PII scrubbed", "light-green", False),
        ("s2", "TRACES\n\n✔ D1 OTel + SDK spans\n✔ D2 Jaeger + OpenSearch\n✔ D3 Content if kept\n✔ D4 Tail sampling", "light-green", False),
        ("s3", "METRICS\n\n✔ D7 Dashboards;\n   internal SLOs only", "light-green", False),
        ("s4", "EXECUTION\n\n✔ D10 Temporal UI\n   + traces", "light-green", False),
        ("s5", "TOKENS\n\n✔ D9 Per tenant,\n   conversation, component\n✔ D13 Estimated", "light-green", False),
        ("s6", "COST / FAILURES\n\n✔ D8 Alerts\n✔ D11 Rules + Jev", "light-green", False),
    ], "light-green")

    # ── Alerts + Jev ────────────────────────────────────────────────────
    y += hs + 30
    hj = row(y, [
        ("alerts", "ALERTS (OB-D8)\n"
                   "• Burn rate on internal SLOs: availability, time to first status,\n"
                   "  time to final reply, escalation rate\n"
                   "• OAuth token expiry · nightly batch failure · breaker open\n"
                   "• Reranker fallback rate · repeated sub-threshold writes in a case", "orange", False),
        ("jev", "JEV IN THIS COMPONENT\n"
                "• Failure categories: Choice over a taxonomy (OB-D11) · use 7\n"
                "• Possible later: alert on drift in Jev confidence · use 9", "yellow", False),
    ], "yellow")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hj + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Raw PII in a log line → MITIGATED (D14 collector scrub)\n"
              "• KK2 Trace context lost across Temporal / Jev / SSE → OWNED (Comp 14)\n"
              "• KK3 Can't delete one user's traces → FIXED (Jaeger + OpenSearch)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Storage for full content → MITIGATED (kept traces, 7 days)\n"
              "• KU2 Tail-sampling collector load → OWNED (Comp 11)\n"
              "• KU3 Jev failure-category accuracy → MITIGATED (EV-D9)",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Ad hoc alerts cause fatigue → MITIGATED (internal SLOs)",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Sampling skews cost numbers → OWNED, accepted (estimates)\n"
              "• UU2 7 days vs. long cases + evaluation → MITIGATED (durable records)\n"
              "• UU3 Forgotten approval workflows → OWNED (Comp 13)",
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
        ("dl1", "CONFIRMED (14 decisions + 3 follow-ups, none open)\n"
                "✔ D1 OTel + SDK spans · D2 Jaeger + OpenSearch · D3 content if kept\n"
                "✔ D4 tail sampling · D5 7 days · D6 erasure by ID · D7 internal SLOs\n"
                "✔ D8 burn-rate + hand-off alerts · D9 tokens per tenant / conversation\n"
                "✔ D10 Temporal UI · D11 rules + Jev categories · D12 JSON logs\n"
                "✔ D13 estimated costs · D14 collector PII scrub", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 9: copy samples within 7 days; Jev category accuracy\n"
                "Comp 11: collector sizing, runbooks, on-call · Comp 12: costs are estimates\n"
                "Comp 13: approval waiting times · Comp 14: trace-context tests\n"
                "Comp 16: owner of the failure taxonomy\n\n"
                "OWNED RISKS TO WATCH\n"
                "UU1 estimated costs · UU3 forgotten workflows · KK2 broken traces\n\n"
                "Full reasoning: checkpoint.md §13", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §13.6 – §13.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")


    # ── Architectural Decision Points (from the checkpoint.md decision log) ──
    add_adp_section(pb, "OB", START_X, TOTAL_W)

    return pb.records("LLD - [9] Observability & Monitoring", "aB")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
