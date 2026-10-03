"""
Generate LLD page for Component [8/15]: Evaluation & Experimentation.

Materializes checkpoint.md §12 (loop step 11): boundary, test environment
tiers, Flow A (a change ships), Flow B (risk scenario) with Flow C (live
quality) and Flow D (rollout), one card per sub-component (mechanic + status),
a Jev note, the Known/Unknown failure grid with step-9 effects (after §12.9a),
and a decision-log summary.

Only the page `page:lld_eval` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, est_h, write_page

PID = "page:lld_eval"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "ev")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [8/15]: EVALUATION & EXPERIMENTATION\n"
        "Framework episodes + opted-in production samples · Component suites + risk-tier end-to-end · "
        "Cross-family LLM judge · Staging / fakes / recordings · Shadow + canary on read-only routes",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Builds + config versions: prompts, Jev questions, thresholds, policies\n"
                 "• Traces + decision records (SG-D13, Comp 10) · retrieval traces (KR)\n"
                 "• Live feedback (Comp 1) · failure reports (13 / 16)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Suite results + release verdicts → CI (Comp 14)\n"
                 "• Calibrated thresholds → config (ADP-05-Q2, SG-D3)\n"
                 "• Quality reports → Observability (10), Improvement (16)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Runtime confidence gate (13) · CI pipeline + software tests (14)\n"
                   "• Dashboards + alerts (10) · acting on findings (16)\n"
                   "• Cost budgets (12)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Environment tiers ───────────────────────────────────────────────
    y += h + 40
    en_y = y
    he = row(en_y + 45, [
        ("e1", "STAGING COPY (EV-D4)\n• Default for every external system\n• Test accounts, outbound allow-list,\n  notifications off (EV-D14)", "light-blue", False),
        ("e2", "STATEFUL FAKE (EV-Q2)\n• Integrations with writes or\n  multi-step workflows\n• e.g. billing, infrastructure", "orange", False),
        ("e3", "RECORDED RESPONSES (EV-Q2)\n• Simple read-only integrations", "light-violet", False),
        ("e4", "SKIP (EV-Q2)\n• Low-priority integrations only\n• Fakes can drift: contract tests\n  → Comp 14 (KU5)", "light-red", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=40)
    en_h = he + 70
    pb.frame_behind("env", "TEST ENVIRONMENT · WHEN NO STAGING COPY EXISTS, BY INTEGRATION TYPE",
                    START_X, en_y, TOTAL_W, en_h, "blue")

    # ── Flow A: a change ships ──────────────────────────────────────────
    y = en_y + en_h + 40
    fa_y = y
    ha = row(fa_y + 45, [
        ("a1", "① Change in code\n• e.g. new triage question wording\n• Prompts, Jev questions, policies\n  are code (DP-D12)", "light-blue", False),
        ("a2", "② Smoke subset per commit\n• Full suites nightly\n  and before release (EV-D6)", "light-blue", False),
        ("a3", "③ Suites (EV-D3)\n• Per-component suites\n• + risk-tier end-to-end episodes\n• Assertions + judge (EV-D2)", "light-violet", False),
        ("a4", "④ Recalibrate (EV-D9)\n• Thresholds per route on labelled sets\n• Jev routes, screening bands,\n  delegation", "yellow", False),
        ("a5", "⑤ Release gate (EV-D5)\n• Component thresholds\n• Zero risk-tier violations, pass^k\n• Cost + latency budgets", "orange", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("a1", "a2"), ("a2", "a3"), ("a3", "a4"), ("a4", "a5")]):
        connect(f"a{i}", s, t, color="green")
    fa_h = ha + 70
    pb.frame_behind("flowA", "FLOW A · A CHANGE SHIPS",
                    START_X, fa_y, TOTAL_W, fa_h, "green")

    # ── Flow B + C + D ──────────────────────────────────────────────────
    y = fa_y + fa_h + 40
    fb_y = y
    hb = row(fb_y + 45, [
        ("b1", "RISK SCENARIO (Flow B)\n• $16,000 SLA credit dispute\n• Assert: no money before approval,\n  no promise before verification\n• Run k times, all must pass", "light-red", False),
        ("b2", "LIVE QUALITY (Flow C)\n• Thumbs, re-asks, escalations\n• Sampled judge scoring (EV-D8)\n• Tokenized, regional, erasable,\n  opted-in tenants only (D10, D15)", "light-blue", False),
        ("b3", "SHADOW (Flow D, EV-D12)\n• New version on live input\n• Reads live; writes recorded,\n  never executed", "light-violet", False),
        ("b4", "CANARY / A/B (EV-D7)\n• Read-only routes only\n• Live evidence counts only for\n  routes it covered (EV-D13)", "orange", False),
        ("b5", "NEXT VERSION'S GATE (EV-D5)\n• Live CSAT, FCR, CES\n• Failures become new test cases\n  (Comp 16)", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("b2", "b3"), ("b3", "b4"), ("b4", "b5")]):
        connect(f"b{i}", s, t, color="violet")
    fb_h = hb + 70
    pb.frame_behind("flowB", "FLOW B · RISK SCENARIO  +  FLOW C · LIVE QUALITY  +  FLOW D · ROLLOUT",
                    START_X, fb_y, TOTAL_W, fb_h, "violet")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = fb_y + fb_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "DATASETS\n\n✔ D1 Episodes + seeds\n   + production\n✔ D10 Tokenized\n✔ D15 Opt-in", "light-green", False),
        ("s2", "FRAMEWORK\n\n✔ D2 Assertions +\n   cross-family judge\n✔ D4 Staging / fakes\n✔ D14 Staging safety", "light-green", False),
        ("s3", "METRICS\n\n✔ D5 Release gate\n✔ D8 Live sampling", "light-green", False),
        ("s4", "RETRIEVAL EVAL\n\n✔ KR-D11 (upstream)\n   golden set + live\n   + judge", "light-green", False),
        ("s5", "AGENT EVAL\n\n✔ D3 Component suites\n   + risk-tier E2E", "light-green", False),
        ("s6", "EXPERIMENTS\n\n✔ D7 Shadow + canary\n✔ D9 Calibration\n✔ D11 Buffered reply\n✔ D12, D13", "light-green", False),
        ("s7", "REGRESSION\n\n✔ D6 Smoke per commit,\n   full nightly + release", "light-green", False),
    ], "light-green")

    # ── Jev note ────────────────────────────────────────────────────────
    y += hs + 30
    hj = row(y, [
        ("jev", "JEV IN THIS COMPONENT\n"
                "• Not a scorer (user chose an LLM judge, EV-D2)\n"
                "• Jev is measured here: accuracy + calibration of every decision point\n"
                "  (triage, guards, tool shortlist / pick / gate, delegation, conflicts, memory) · EV-D9", "yellow", False),
        ("ux", "STREAMING (EV-D11, resolves UA-D8)\n"
               "• Reply buffered until all checks pass\n"
               "• 'status' events meanwhile\n"
               "• Wait time measured (KU4)", "light-blue", False),
    ], "yellow")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hj + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Staging down → nightly fails for other reasons → OWNED (Comp 11 / 14)\n"
              "• KK2 Staging state carries over → OWNED (resets → Comp 14)\n"
              "• KK3 Erasure misses eval copies → FIXED (D10)\n"
              "• KK4 Same conversation in few-shot and tests → OWNED (Comp 16)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Judge cost → OWNED (Comp 12)\n"
              "• KU2 Judge vs. human agreement → MITIGATED (human sample)\n"
              "• KU3 Too few labels on rare routes → OWNED\n"
              "• KU4 Wait for buffered reply → MITIGATED (status events)\n"
              "• KU5 Fakes drift from real systems → OWNED (Comp 14)",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Staging causes real side effects → MITIGATED (D14)\n"
              "• UK2 Contracts forbid using conversations → FIXED (D15 opt-in)",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Untested integration → MITIGATED (risk-tier E2E)\n"
              "• UU2 Canary on low-risk approves high-risk → FIXED (D13)\n"
              "• UU3 Judge favours its own model → MITIGATED (other family)\n"
              "• UU4 Tokenized test data → OWNED, accepted\n"
              "• UU5 Shadow duplicates writes → FIXED (D12)",
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
        ("dl1", "CONFIRMED (15 decisions + 4 follow-ups, none open)\n"
                "✔ D1 episodes + production · D2 cross-family judge · D3 components + risk E2E\n"
                "✔ D4 staging / fakes / recordings · D5 release gate · D6 cadence\n"
                "✔ D7 shadow + read-only canary · D8 live sampling · D9 calibration\n"
                "✔ D10 tokenized data · D11 buffered reply (UA-D8) · D12 shadow writes off\n"
                "✔ D13 route-scoped evidence · D14 staging safety · D15 opt-in", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 1: status events, CSAT / CES, opt-in UI · Comp 5: integration criticality\n"
                "Comp 10: live signals · Comp 11: staging, buffered-reply latency, shadow load\n"
                "Comp 12: judge cost · Comp 13: runtime confidence gate\n"
                "Comp 14: CI suites, staging resets, fake contract tests · Comp 16: few-shot vs. tests\n\n"
                "OWNED RISKS TO WATCH\n"
                "KK1 staging flakiness · KU5 fakes drift · KU1 judge cost\n\n"
                "Full reasoning: checkpoint.md §12", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §12.6 – §12.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")

    return pb.records("LLD - [8] Evaluation & Experimentation", "aA")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
