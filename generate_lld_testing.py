"""
Generate LLD page for Component [13/15]: Testing & Quality.

Materializes checkpoint.md §17 (loop step 11): the boundary with Evaluation,
the safety invariants under test, the pipeline (pull request → merge gate →
nightly → release), one card per sub-component (mechanic + status), the
Known/Unknown failure grid with step-9 effects (after §17.9a), and a
decision-log summary.

Only the page `page:lld_testing` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, est_h, write_page

PID = "page:lld_testing"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "tq")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [13/15]: TESTING & QUALITY\n"
        "Mocked models · Property tests of safety invariants · Contracts · Policy + RLS checks in CI · "
        "8 scenario E2E tests · No retries for safety tests",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Pull requests: code, prompts, Jev questions,\n"
                 "  policies, migrations\n"
                 "• Evaluation suites + verdicts (Comp 9)\n"
                 "• Staging + fakes (EV-D4)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Merge + release verdicts → Deployment (15)\n"
                 "• Failures → owners\n"
                 "• Test-run telemetry → Observability (10)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Quality scoring + calibration (9): what a model says\n"
                   "• Deploying + rolling back (15)\n"
                   "• Production alerting (10) · fixing failures (16)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Invariants ──────────────────────────────────────────────────────
    y += h + 40
    iv_y = y
    hi = row(iv_y + 45, [
        ("i1", "MONEY\n• No financial write ≥ threshold\n  without approval (TA-D5)\n• Approver ≠ handler (HL-D4)", "light-red", False),
        ("i2", "REPLIES\n• No reply before checks (EV-D11)\n• Success only after read-back\n  (MA-D14)", "orange", False),
        ("i3", "CONCURRENCY\n• One active turn (RP-D3)\n• Specialists write only alone\n  (MA-D18) · cancel vs. approve", "light-violet", False),
        ("i4", "DATA\n• Models see PII tokens only (SG-D4)\n• Tenant isolation (DP-D2)\n• Writes denied if Cedar down (SG-D17)", "light-blue", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=40)
    iv_h = hi + 70
    pb.frame_behind("inv", "SAFETY INVARIANTS · property-based tests over random model outputs (TQ-D2) · never retried (TQ-D13)",
                    START_X, iv_y, TOTAL_W, iv_h, "red")

    # ── Pipeline ────────────────────────────────────────────────────────
    y = iv_y + iv_h + 40
    pl_y = y
    hp = row(pl_y + 45, [
        ("p1", "① Pull request\n• Unit tests, models mocked\n  (TQ-D1)\n• Agent-behaviour + property tests", "light-blue", False),
        ("p2", "② Merge gate (TQ-D9)\n• Integration + contracts (TQ-D5)\n• Policy + RLS + tool checks (TQ-D4)\n• Trace test (TQ-D11) · EV smoke", "orange", False),
        ("p3", "③ Nightly (EV-D6)\n• Full EV suites on staging\n• 8 scenario E2E tests (TQ-D6)\n• Fixed injection set (TQ-D3)", "light-violet", False),
        ("p4", "④ Release\n• Load + chaos on staging (TQ-D10)\n• EV release gate (EV-D5)\n• Old checkpoints load (TQ-D14)", "light-green", False),
        ("p5", "FLAKY TESTS (TQ-D8, D13)\n• Retried automatically\n• Except invariant, property,\n  policy, security tests", "yellow", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("p1", "p2"), ("p2", "p3"), ("p3", "p4")]):
        connect(f"p{i}", s, t, color="green")
    pl_h = hp + 70
    pb.frame_behind("pipe", "FLOWS A–D · PULL REQUEST → MERGE GATE → NIGHTLY → RELEASE · Test data: synthetic personas + tokenized opted-in samples (TQ-D12)",
                    START_X, pl_y, TOTAL_W, pl_h, "green")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = pl_y + pl_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS  ·  No Jev use (calls mocked; question sets contract-tested)", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "UNIT\n\n✔ D1 Models mocked\n✔ D4 Cedar tests", "light-green", False),
        ("s2", "INTEGRATION\n\n✔ D5 Contracts\n✔ D11 One trace", "light-green", False),
        ("s3", "E2E\n\n✔ D6 8 scenarios\n✔ D12 Persona + samples", "light-green", False),
        ("s4", "AGENT BEHAVIOR\n\n✔ D2 Scripted outputs\n   + property tests", "light-green", False),
        ("s5", "ADVERSARIAL\n\n✔ D3 Fixed injection set", "light-green", False),
        ("s6", "REGRESSION\n\n✔ D7, D14 Migrations\n✔ D8, D13 Retries\n✔ D9 Merge gate\n✔ D10 Load + chaos", "light-green", False),
    ], "light-green")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hs + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Tenant table without RLS → FIXED (CI check)\n"
              "• KK2 Tool without risk class / needs_pii → FIXED (CI check)\n"
              "• KK3 Shared format change breaks others → FIXED (contracts)\n"
              "• KK4 Migration breaks code / old checkpoints → MITIGATED (D14)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Merge time + model cost → OWNED (Comp 12 / 15)\n"
              "• KU2 Random outputs miss rare states → MITIGATED (scripted cases)\n"
              "• KU3 Injection set goes stale → OWNED, accepted",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 No fresh attacks before big releases → OWNED, accepted",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Retries hide races → FIXED (D13)\n"
              "• UU2 Mocks drift from real models → MITIGATED (EV uses real models)\n"
              "• UU3 Erased users in staging fixtures → MITIGATED (erasure inventory)",
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
        ("dl1", "CONFIRMED (14 decisions, none open)\n"
                "✔ D1 mocked models · D2 property tests · D3 fixed injection set\n"
                "✔ D4 policy + RLS + tool checks · D5 contracts · D6 8 scenario E2E\n"
                "✔ D7 SQL migrations by review · D8 retries · D9 merge gate\n"
                "✔ D10 load + chaos on staging · D11 trace tests · D12 test data\n"
                "✔ D13 no retries for safety tests · D14 old checkpoints load", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 8: staging fixtures in the erasure inventory\n"
                "Comp 12: model cost of the merge gate\n"
                "Comp 15: merge / release verdicts, merge time, checkpoint sample library\n\n"
                "Full reasoning: checkpoint.md §17", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §17.6 – §17.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")

    return pb.records("LLD - [13] Testing & Quality", "aF")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
