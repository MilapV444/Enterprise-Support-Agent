"""
Generate LLD page for Component [3/15]: Memory & State.

Materializes checkpoint.md §7 (loop step 11): boundary, Flow A (one turn),
Flow B (consolidation), Flow C (long wait + resume) with Flow D (lifecycle),
one card per sub-component (mechanic + status), Jev placements, the
Known/Unknown failure grid with step-9 effects (after §7.9a), and a
decision-log summary.

Only the page `page:lld_memory` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, add_adp_section, est_h, write_page

PID = "page:lld_memory"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "ms")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [3/15]: MEMORY & STATE\n"
        "Session → conversation → case · Verbatim + summary + pins · Per-user facts with validity dates · "
        "Jev reconcile · LangGraph checkpoints · Fixed TTLs",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Turns + state changes from Orchestration (Comp 2),\n"
                 "  with conversation, case, user, tenant, tier (Comp 1)\n"
                 "• Tool results (Comp 5) · delivered replies (Comp 1)\n"
                 "• Erasure / correction / retention rules (Comp 7 / 8)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Dialogue (25%) + facts (15%) + scratchpad (10%) → Orchestration\n"
                 "• Restored checkpoints → Orchestration / Temporal\n"
                 "• Memory-write + erasure events → Data (8), Observability (10)\n"
                 "• Resolved episodes → Improvement (16)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Slot budgets + packing (ADP-03) · timers + waits (Temporal)\n"
                   "• Session identity + expiry (1) · documents + tickets (Knowledge)\n"
                   "• Account data: SLA, plan, invoices = CRM tool (5)\n"
                   "• Retention / PII policy (7 / 8) · storage engines (8) · cache (12)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Flow A: one turn ────────────────────────────────────────────────
    y += h + 40
    fa_y = y
    r1_y = fa_y + 45
    h1 = row(r1_y, [
        ("a0", "NOT OWNED →\nOrchestration receives the turn\n(conversation, case, user from token)", None, True),
        ("a1", "① Load Agent State (MS-D8)\n• LangGraph checkpoint from Postgres\n• FSM node, parameters, counters\n• Version check + migration (D13)", "light-blue", False),
        ("a2", "② Conversation Memory (MS-D2)\n• Last N turns verbatim\n• Rolling summary of older turns\n• Pinned items, never evicted", "light-blue", False),
        ("a3", "③ Long-Term Facts (D3, D4)\n• This user's facts valid now\n• Preferences, past episodes\n• Account facts: NOT here (D6 → CRM)", "light-blue", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    r2_y = r1_y + h1 + 70
    h2 = row(r2_y, [
        ("a7", "⑦ Append Turn\n• User turn + delivered reply\n• Pin check: rules + Jev Noul (Q2)\n• Unpin if withdrawn (Jev)", "light-green", False),
        ("a6", "⑥ Checkpoint (MS-D9)\n• After every graph node\n• Before + after each tool that changes data\n• Idempotency key → Comp 5", "orange", False),
        ("a5", "⑤ Working Memory (MS-D7)\n• Plan, tool outputs, passage refs\n• 40 KB ledger stored by reference\n• Inline summary; page in on demand", "light-violet", False),
        ("a4", "NOT OWNED ←\nOrchestration packs the slots (ADP-03)\n25% dialogue · 15% facts · 10% scratchpad", None, True),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    fa_h = (r2_y + h2 + 25) - fa_y
    pb.frame_behind("flowA", "FLOW A · HOT PATH: ONE TURN (Sarah @ acme-corp, T2, case INV-9821)",
                    START_X, fa_y, TOTAL_W, fa_h, "green")
    for i, (s, t) in enumerate([("a0", "a1"), ("a1", "a2"), ("a2", "a3")]):
        connect(f"a{i}", s, t, color="blue")
    connect("turn", "a3", "a4", fa="B", ta="T", color="grey", label="content")
    for i, (s, t) in enumerate([("a4", "a5"), ("a5", "a6"), ("a6", "a7")]):
        connect(f"b{i}", s, t, fa="L", ta="R", color="green")

    # ── Flow B: consolidation ───────────────────────────────────────────
    y = fa_y + fa_h + 40
    fb_y = y
    hb = row(fb_y + 45, [
        ("c1", "① Trigger (MS-Q4)\n• Case resolved\n• No case: 24 h idle close\n• Case open > 14 days: each conversation close", "light-blue", False),
        ("c2", "② Extract (MS-D5, D16, D17)\n• LLM reads user turns only\n• + allow-listed structured tool fields\n• Skips plans; never retrieved docs", "light-violet", False),
        ("c3", "③ About the user? (MS-D15)\n• Jev Noul per candidate\n• Facts about others dropped", "yellow", False),
        ("c4", "④ Reconcile (MS-D12, D19)\n• Mask candidate + nearest facts alike\n• Jev Choice: ADD / UPDATE / DELETE / NOOP\n• Low confidence → NOOP", "yellow", False),
        ("c5", "⑤ Write (MS-D4)\n• UPDATE / DELETE close valid_to\n• Stored unmasked, encrypted\n• Event → audit (8), traces (10)", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("c1", "c2"), ("c2", "c3"), ("c3", "c4"), ("c4", "c5")]):
        connect(f"c{i}", s, t, color="violet")
    fb_h = hb + 70
    pb.frame_behind("flowB", "FLOW B · CONSOLIDATION (async, after resolution)",
                    START_X, fb_y, TOTAL_W, fb_h, "violet")

    # ── Flow C + D: long wait, resume, lifecycle ────────────────────────
    y = fb_y + fb_h + 40
    fc_y = y
    hc = row(fc_y + 45, [
        ("d1", "① Wait (MS-D8)\n• Graph at AWAITING_APPROVAL\n• Checkpoint committed\n• Temporal holds only status + checkpoint ID", "light-blue", False),
        ("d2", "② Session expires (UA-D6)\n• Conversation, case and state persist", "light-blue", False),
        ("d3", "③ Resume, 3 h later (MS-D18)\n• Wait > 1 h → re-fetch tool data\n• Re-check pre-conditions\n• Then continue; no tool re-run", "orange", False),
        ("d4", "④ Next day, new conversation (MS-D1)\n• Jev Choice over open cases (Q1)\n• Confirm when not high confidence\n• Links to case INV-9821", "yellow", False),
        ("d5", "LIFECYCLE (Flow D)\n• Fixed TTLs (D10, Q3)\n• Back-office erase / correct (D11)\n• Erasure inventory, every store (D14)", "light-red", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("d1", "d2"), ("d2", "d3"), ("d3", "d4")]):
        connect(f"d{i}", s, t, color="blue")
    fc_h = hc + 70
    pb.frame_behind("flowC", "FLOW C · LONG WAIT & RESUME ($12,400 credit memo approval)  +  FLOW D · LIFECYCLE",
                    START_X, fc_y, TOTAL_W, fc_h, "blue")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = fc_y + fc_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "CONVERSATION MEMORY\nOrdered turn log + compaction.\n\n✔ D1 Session → conversation → case\n✔ D2 Verbatim + summary + pins\n✔ Q1 Jev case linking\n✔ Q2 Rules + Jev pins", "light-green", False),
        ("s2", "LONG-TERM MEMORY\nFacts, preferences, episodes about a user.\n\n✔ D3 Per-user only · D4 validity dates\n✔ D5 At resolution · D6 no account facts\n✔ D12 Jev reconcile · D15 subject check\n✔ D16 allow-listed tools · D17 no plans\n✔ D19 unmasked, encrypted", "light-green", False),
        ("s3", "WORKING MEMORY\nWhat one run holds between steps.\n\n✔ D7 Large outputs by reference + summary", "light-green", False),
        ("s4", "AGENT STATE\nDurable execution state for crash recovery and resume.\n\n✔ D8 LangGraph checkpointer is the truth\n✔ D9 Per node + around data-changing tools\n✔ D13 Versioned checkpoints\n✔ D18 Re-check after waits > 1 h", "light-green", False),
        ("s5", "MEMORY LIFECYCLE\nRetention, correction, erasure, audit.\n\n✔ D10 Fixed TTLs (Q3)\n✔ D11 Back-office in v1\n✔ D14 Erasure inventory", "light-green", False),
    ], "light-green")

    # ── Jev placements ──────────────────────────────────────────────────
    y += hs + 30
    hj = row(y, [
        ("jev", "JEV IN THIS COMPONENT (ADP-05, masked input only)\n"
                "• Reconcile: Choice ADD / UPDATE / DELETE / NOOP (D12) · uses 4, 7, 9\n"
                "• Case linking: Choice over open cases, confirm below high confidence (Q1) · uses 4, 9\n"
                "• Pinning / unpinning: Noul per sentence (Q2) · use 7\n"
                "• Subject check: Noul 'is this about the user?' (D15) · uses 2, 7", "yellow", False),
        ("nojev", "NOT JEV\n"
                  "• Rolling summaries + fact extraction: text generation → LLM\n"
                  "• TTLs, validity dates, 1 h / 24 h / 14 d rules: date math → code\n"
                  "• Checkpoint versions + migrations: deterministic → code", "light-red", False),
    ], "yellow")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hj + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Crash after a refund, before the checkpoint → FIXED if tools honour idempotency keys (D9, Comp 5)\n"
              "• KK2 Facts loaded for the wrong user → MITIGATED (user from token)\n"
              "• KK3 Two tabs write one conversation at once → OWNED (write ordering)\n"
              "• KK4 Schema change breaks a paused checkpoint → FIXED (D13)\n"
              "• KK5 Erasure misses copies → MITIGATED (D14; provider logs → Comp 7)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Summary drift over long cases → MITIGATED (pins)\n"
              "• KU2 Extraction / reconcile accuracy → MITIGATED (low confidence → NOOP)\n"
              "• KU3 Checkpoint write volume → OWNED (load test, Comp 8)\n"
              "• KU4 Wrong case link → MITIGATED (user confirms, Q1)\n"
              "• KU5 TTLs too short / too long → OWNED, accepted",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Creepy recall of old issues → MITIGATED (TTLs; tone rule → Comp 7)\n"
              "• UK2 Facts about colleagues stored → MITIGATED (D15 subject check)\n"
              "• UK3 Facts follow a user who left the company → FIXED (D14 user + tenant key)\n"
              "• UK4 Withdrawn constraint stays pinned → MITIGATED (Jev unpin, Q2)",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Instruction in tool text stored as a fact → MITIGATED (D16 structured fields only)\n"
              "• UU2 Plans stored as facts → MITIGATED (D17 extractor skips plans)\n"
              "• UU3 Resume acts on stale data → MITIGATED (D18 re-check after > 1 h)\n"
              "• UU4 Long-open cases learn nothing → MITIGATED (Q4 > 14 days)\n"
              "• UU5 Jev compares masked vs. unmasked → FIXED (D19 mask both sides)",
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
        ("dl1", "CONFIRMED (18 decisions + 4 follow-ups, none open)\n"
                "✔ D1 session → conversation → case · D2 verbatim + summary + pins\n"
                "✔ D3 per-user facts · D4 validity dates · D5 extract at resolution\n"
                "✔ D6 account facts from CRM · D7 outputs by reference · D8 LangGraph state\n"
                "✔ D9 checkpoints around tools · D10 fixed TTLs · D11 back-office erasure\n"
                "✔ D12 Jev reconcile · D13 versioned checkpoints · D14 erasure inventory\n"
                "✔ D15 subject check · D16 allow-listed tools · D17 no plans · D18 re-check · D19 mask both", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 5: idempotency keys (D9); fact allow-list review (D16)\n"
                "Comp 7: LLM / Jev provider log retention (D14); 'don't raise old issues' tone rule (UK1)\n"
                "Comp 8: Postgres sizing (KU3), blob store (D7), fact encryption (D19)\n"
                "Comp 9: memory + case-link tests (KU2, KU4) · Comp 10: trace purge (D14)\n\n"
                "OWNED RISKS TO WATCH\n"
                "KK3 concurrent writes · KU3 checkpoint volume · KU5 TTL sizing\n\n"
                "Full reasoning: checkpoint.md §7", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §7.6 – §7.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")


    # ── Architectural Decision Points (from the checkpoint.md decision log) ──
    add_adp_section(pb, "MS", START_X, TOTAL_W)

    return pb.records("LLD - [3] Memory & State", "a5")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
