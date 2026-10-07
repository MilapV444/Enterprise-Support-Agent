"""
Generate LLD page for Component [12/15]: Human-in-the-Loop.

Materializes checkpoint.md §16 (loop step 11): boundary, the confidence gate
and its bands, escalation sources → packet → queues, Flow B (approval of the
$12,400 credit), handoff and waiting, one card per sub-component (mechanic +
status), Jev placements, the Known/Unknown failure grid with step-9 effects
(after §16.9a), and a decision-log summary.

Only the page `page:lld_hitl` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, add_adp_section, est_h, write_page

PID = "page:lld_hitl"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "hl")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [12/15]: HUMAN-IN-THE-LOOP\n"
        "Jev draft gate · Send / co-pilot / hand off · One escalation packet · Skills queues with SLAs · "
        "Approval by role and amount · Field-by-field approval · Cold handoff · Retool per region",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Draft replies + evidence (coordinator)\n"
                 "• Approval-required calls + dry-run previews (Tools)\n"
                 "• Escalations: Tools, Multi-Agent, Safety, Memory, Reliability\n"
                 "• 'Talk to a human' (Comp 1) · triage acuity (Jev)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Gate verdicts → Orchestration / Delivery\n"
                 "• Approval / cancel signals → Temporal (Tools executes)\n"
                 "• Human replies → conversation (Comp 1)\n"
                 "• Reason codes → Evaluation (9), Improvement (16)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Executing actions (Tools) · output checks (Safety)\n"
                   "• Calibrating thresholds (EV-D9)\n"
                   "• Staffing (operations) · rendering (Comp 1)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Gate ────────────────────────────────────────────────────────────
    y += h + 40
    ga_y = y
    hg = row(ga_y + 45, [
        ("g1", "① Draft (coordinator)\n• Passed output checks\n  (SG-D6, D15)", "light-blue", False),
        ("g2", "② Jev gate (HL-D1)\n• Noul: claims supported?\n• Score: relevance\n• Agent-written evidence counts less", "yellow", False),
        ("g3", "③ Numbers rule (HL-D13)\n• Money or SLA figures\n  → co-pilot band", "orange", False),
        ("g4", "④ Bands (HL-D2)\n• ≥ 0.90 send\n• 0.50–0.90 co-pilot (staffed routes)\n• < 0.50 hand off", "light-violet", False),
        ("g5", "⑤ Out\n• Send → Delivery\n• Co-pilot: human edits, then send\n• Hand off → escalation packet", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("g1", "g2"), ("g2", "g3"), ("g3", "g4"), ("g4", "g5")]):
        connect(f"g{i}", s, t, color="green")
    ga_h = hg + 70
    pb.frame_behind("gate", "FLOW A · CONFIDENCE GATE ON A DRAFT",
                    START_X, ga_y, TOTAL_W, ga_h, "green")

    # ── Escalation + approval ───────────────────────────────────────────
    y = ga_y + ga_h + 40
    es_y = y
    he = row(es_y + 45, [
        ("e1", "SOURCES\n• Approvals (TA-D5, D16, D18, SG-D10)\n• Low confidence / blocked / numbers\n  (MA-D3, D4, D16, TA-Q3)\n• Review band, significant decisions\n  (SG-D3, D14) · 24 h holds (RP-D7)", "light-blue", False),
        ("e2", "PACKET (HL-D12)\n• Reason code, case, summary\n• Evidence refs, proposed action\n• Diagnostic, deadline", "light-violet", False),
        ("e3", "QUEUES (HL-D3)\n• Billing · technical · account; tier\n• Priority: Jev acuity + tenant tier\n• SLA: handoff 15 min, approval 1 h,\n  review 1 business day → senior", "orange", False),
        ("e4", "APPROVAL (HL-D4, D5)\n• Senior ≥ tenant amount (default $5,000)\n• Approver ≠ handler (Cedar)\n• Confirm amount, account, target\n• Signal → Temporal; first signal wins", "yellow", False),
        ("e5", "STUCK (HL-D9)\n• Aging alerts to the queue lead\n• Undecided after 3 days → cancelled,\n  user told + offered review", "light-red", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("e1", "e2"), ("e2", "e3"), ("e3", "e4")]):
        connect(f"e{i}", s, t, color="violet")
    es_h = he + 70
    pb.frame_behind("esc", "FLOW B · ESCALATION + APPROVAL ($12,400 credit for Sarah → billing senior queue)",
                    START_X, es_y, TOTAL_W, es_h, "violet")

    # ── Handoff ─────────────────────────────────────────────────────────
    y = es_y + es_h + 40
    ho_y = y
    hh = row(ho_y + 45, [
        ("h1", "'TALK TO A HUMAN' (HL-D7)\n• Button or Jev Noul detects it\n• Immediate handoff", "yellow", False),
        ("h2", "WAITING (HL-D7, D8)\n• Agent answers low-risk questions\n• Status, wait estimate, cancel", "light-blue", False),
        ("h3", "COLD HANDOFF (HL-D6)\n• Human takes over from the packet\n• Agent stops", "orange", False),
        ("h4", "HUMAN REPLIES (HL-D14)\n• Same output checks as warnings\n• Override with a logged reason", "light-red", False),
        ("h5", "FEEDBACK (HL-D10)\n• Approve / reject\n• Reason code on reject or edit\n• → Evaluation, Improvement", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("h1", "h2"), ("h2", "h3"), ("h3", "h4")]):
        connect(f"h{i}", s, t, color="blue")
    ho_h = hh + 70
    pb.frame_behind("handoff", "FLOWS C–E · HANDOFF, WAITING, FEEDBACK · Console: self-hosted Retool per region (HL-D11)",
                    START_X, ho_y, TOTAL_W, ho_h, "blue")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = ho_y + ho_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "CONFIDENCE BOUNDARIES\n\n✔ D1 Jev draft gate\n✔ D2 Three bands\n✔ D13 Numbers → co-pilot", "light-green", False),
        ("s2", "ESCALATION\n\n✔ D3 Skills queues + SLAs\n✔ D9 Aging + 3-day cancel\n✔ D12 One packet\n✔ D11 Retool per region", "light-green", False),
        ("s3", "APPROVAL\n\n✔ D4 Role + amount\n✔ D5 Field-by-field", "light-green", False),
        ("s4", "HANDOFF\n\n✔ D6 Cold\n✔ D7 Human on request\n✔ D8 Wait estimate + cancel\n✔ D14 Checks on human replies", "light-green", False),
        ("s5", "HUMAN FEEDBACK\n\n✔ D10 Reason codes", "light-green", False),
    ], "light-green")

    # ── Jev placements ──────────────────────────────────────────────────
    y += hs + 30
    hj = row(y, [
        ("jev", "JEV IN THIS COMPONENT (masked input only)\n"
                "• Draft gate: Noul claims supported + Score relevance (HL-D1) · uses 6, 9\n"
                "• 'Is the user asking for a human?' Noul (HL-D7) · use 4\n"
                "• Queue priority: triage acuity Score reused (HL-D3) · use 4", "yellow", False),
        ("nojev", "NOT JEV\n"
                  "• Money / SLA figures: always a human (HL-D13)\n"
                  "• Amount rules, timers, signal ordering: code", "light-red", False),
    ], "yellow")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hj + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Approval signal lost / duplicated → FIXED (Temporal + idempotency)\n"
              "• KK2 Wrong approver → FIXED (Cedar policy)\n"
              "• KK3 Escalation without evidence → FIXED (typed packet)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Jev gate accuracy → MITIGATED (EV calibration)\n"
              "• KU2 Human workload → OWNED (worsened by D13; operations)\n"
              "• KU3 Retool limits at scale → OWNED",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Automation bias → MITIGATED (field-by-field)\n"
              "• UK2 Repeating yourself after transfer → MITIGATED (packet summary)\n"
              "• UK3 Specialist pastes internal notes → MITIGATED (D14 warnings)",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Wrong numbers pass the gate → FIXED (D13)\n"
              "• UU2 Cancel vs. approve race → MITIGATED (first signal wins)\n"
              "• UU3 Auto-cancel = silent refusal → MITIGATED (told + review offer)\n"
              "• UU4 Middle band floods handoffs → MITIGATED (calibration)\n"
              "• UU5 Missed 'I want a human' → MITIGATED (button always shown)",
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
        ("dl1", "CONFIRMED (14 decisions + 5 follow-ups, none open)\n"
                "✔ D1 Jev gate · D2 bands 0.90 / 0.50 · D3 skills queues + SLAs\n"
                "✔ D4 senior ≥ $5,000 default, approver ≠ handler · D5 field-by-field\n"
                "✔ D6 cold handoff · D7 human on request · D8 wait estimate + cancel\n"
                "✔ D9 3-day cancel · D10 reason codes · D11 Retool per region\n"
                "✔ D12 one packet · D13 money / SLA → human · D14 checks on human replies", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 1: wait estimate, cancel, 'talk to a human', in-review status\n"
                "Comp 7: Cedar approval rights, checks on human replies\n"
                "Comp 8: tenant senior amount, packets with the case\n"
                "Comp 9: gate calibration, reason codes as labels\n"
                "Comp 10: queue size, SLA breaches, overrides · Operations: staffing\n\n"
                "Full reasoning: checkpoint.md §16", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §16.6 – §16.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")


    # ── Architectural Decision Points (from the checkpoint.md decision log) ──
    add_adp_section(pb, "HL", START_X, TOTAL_W)

    return pb.records("LLD - [12] Human-in-the-Loop", "aE")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
