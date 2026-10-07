"""
Generate LLD page for Component [15/15]: Continuous Improvement.

Materializes checkpoint.md §19 (loop step 11): boundary, the improvement loop
(signals → analysis → fix → test → validate → ship), levers, the fine-tuning
track, evolution reviews, one card per sub-component (mechanic + status), the
Known/Unknown failure grid with step-9 effects (after §19.9a), and a
decision-log summary.

Only the page `page:lld_improvement` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, est_h, write_page

PID = "page:lld_improvement"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "ci")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [15/15]: CONTINUOUS IMPROVEMENT\n"
        "Signals + survey · Jev feedback triage · Hierarchical taxonomy · Every failure → test · "
        "Gate + before / after + A/B · Per-region fine-tuning, retrained quarterly",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Feedback + implicit signals (Comp 1, 10)\n"
                 "• Reason codes (13) · failure categories (10)\n"
                 "• Quality reports (9) · gap signals (3) · cost (12)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Fixes as pull requests → tests (13), releases (15)\n"
                 "• New test episodes → Evaluation (9)\n"
                 "• Article drafts → Knowledge (3), human review", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Measuring quality (9) · telemetry (10)\n"
                   "• Releasing (15) · indexing knowledge (3)\n"
                   "• Approving actions (13)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── The loop ────────────────────────────────────────────────────────
    y += h + 40
    lp_y = y
    r1_y = lp_y + 45
    h1 = row(r1_y, [
        ("l1", "① Signals (CI-D1)\n• Thumbs, reason codes\n• Re-asks, escalations, abandonment,\n  reopened cases\n• Survey after resolution", "light-blue", False),
        ("l2", "② Classify (CI-D11, OB-D11)\n• Jev Choice: failure category\n• Jev Score: severity\n• Manual check on a sample", "yellow", False),
        ("l3", "③ Analyse (CI-D2, D3)\n• Hierarchical taxonomy, in code\n• Weekly review: volume × severity\n• Postmortems: safety / money", "orange", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    r2_y = r1_y + h1 + 70
    h2 = row(r2_y, [
        ("l6", "⑥ Ship (DL-D10)\n• Scheduled behaviour release\n• Shadow → canary → all", "light-green", False),
        ("l5", "⑤ Validate (CI-D8)\n• Release gate (EV-D5)\n• Before / after on the cluster\n• A/B on read-only routes", "light-violet", False),
        ("l4", "④ Test, then fix (CI-D7, D4)\n• Failure → test before the fix\n• Clustered tests\n• Normal code review (CI-D10)", "light-red", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("l1", "l2"), ("l2", "l3")]):
        connect(f"a{i}", s, t, color="blue")
    connect("turn", "l3", "l4", fa="B", ta="T", color="grey", label="owner")
    for i, (s, t) in enumerate([("l4", "l5"), ("l5", "l6")]):
        connect(f"b{i}", s, t, fa="L", ta="R", color="green")
    lp_h = (r2_y + h2 + 25) - lp_y
    pb.frame_behind("loop", "FLOWS A–B · THE IMPROVEMENT LOOP (e.g. 'told me to contact billing again' rising)",
                    START_X, lp_y, TOTAL_W, lp_h, "green")

    # ── Levers + evolution ──────────────────────────────────────────────
    y = lp_y + lp_h + 40
    lv_y = y
    hl = row(lv_y + 45, [
        ("v1", "LEVERS (CI-D4)\n• Prompts, Jev questions, thresholds\n• Tool descriptions\n• KB articles, few-shot examples", "light-blue", False),
        ("v2", "ARTICLES (CI-D6, Flow C)\n• Agent drafts from resolved cases\n• Internal by default (KR-D13)\n• Human reviews + publishes", "light-violet", False),
        ("v3", "FEW-SHOT (CI-D5, Flow D)\n• Curated per route, tokenized\n• Never in test sets", "light-green", False),
        ("v4", "FINE-TUNING (CI-D4, Q1, Q2, D12)\n• Self-hosted model, per region\n• Opted-in, tokenized, positively\n  signalled conversations\n• Retrained quarterly without\n  erased users", "orange", False),
        ("v5", "EVOLUTION (CI-D9, Flow E)\n• Monthly: observed vs. assumed\n  users → eval sampling\n• Quarterly: review of all owned\n  risks in checkpoint.md", "yellow", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=40)
    lv_h = hl + 70
    pb.frame_behind("levers", "FLOWS C–E · LEVERS, FINE-TUNING, EVOLUTION",
                    START_X, lv_y, TOTAL_W, lv_h, "violet")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = lv_y + lv_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS  ·  Jev: feedback category + severity (use 7)", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "PRODUCTION FEEDBACK\n\n✔ D1 Signals + survey\n✔ D11 Jev triage", "light-green", False),
        ("s2", "FAILURE ANALYSIS\n\n✔ D2 Taxonomy\n✔ D3 Reviews +\n   postmortems", "light-green", False),
        ("s3", "EXPERIMENTATION\n\n✔ D8 A/B on\n   read-only routes", "light-green", False),
        ("s4", "IMPROVEMENT\n\n✔ D4 Levers + fine-tune\n✔ D5 Few-shot · D6 articles\n✔ D10 Code review\n✔ D12 Quarterly retrain", "light-green", False),
        ("s5", "VALIDATION\n\n✔ D7 Failure → test\n✔ D8 Gate + before / after", "light-green", False),
        ("s6", "EVOLUTION\n\n✔ D9 Monthly drift +\n   quarterly risk review", "light-green", False),
    ], "light-green")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hs + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Few-shot example is also a test → FIXED (D5)\n"
              "• KK2 Fix ships without a test → FIXED (D7)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Survey response bias → MITIGATED (implicit signals)\n"
              "• KU2 Jev category / severity accuracy → MITIGATED (EV-D9)\n"
              "• KU3 Fine-tuning gain vs. cost → OWNED (Comp 12)",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Agent drafts carry agent errors into the KB → MITIGATED (review)\n"
              "• UK2 No dedicated sign-off for safety / money → OWNED, accepted",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Erased data stays in weights → MITIGATED (quarterly retrain)\n"
              "• UU2 Training across regions → FIXED (per-region models)\n"
              "• UU3 Self-reinforcing training → MITIGATED (positive signals only)",
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
        ("dl1", "CONFIRMED (12 decisions + 2 follow-ups, none open)\n"
                "✔ D1 signals + survey · D2 taxonomy · D3 reviews + postmortems\n"
                "✔ D4 levers + per-region fine-tuning · D5 few-shot · D6 articles\n"
                "✔ D7 failure → test · D8 gate + before / after + A/B\n"
                "✔ D9 drift + risk reviews · D10 code review · D11 Jev triage\n"
                "✔ D12 quarterly retrain without erased users", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 1: survey UI, updated training terms\n"
                "Comp 8: training sets in the erasure inventory\n"
                "Comp 9: fine-tuned baselines · Comp 10: implicit signals\n"
                "Comp 12: GPU cost · Comp 15: weights on the model track\n\n"
                "ALL 15 COMPONENT LOOPS CLOSED · Full reasoning: checkpoint.md §19, §20", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §19.6 – §19.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")

    return pb.records("LLD - [15] Continuous Improvement", "aH")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
