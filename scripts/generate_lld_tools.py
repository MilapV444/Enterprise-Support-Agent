"""
Generate LLD page for Component [4/15]: Tools & Actions.

Materializes checkpoint.md §8 (loop step 11): boundary, Flow A (read),
Flow B (write with approval), Flow C (failure + saga rollback) with Flow D
(onboarding), one card per sub-component (mechanic + status), Jev placements,
the Known/Unknown failure grid with step-9 effects (after §8.9a), and a
decision-log summary.

Only the page `page:lld_tools` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, est_h, write_page

PID = "page:lld_tools"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "ta")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [4/15]: TOOLS & ACTIONS\n"
        "Jev shortlist + pick · Python tools as Temporal activities · Argument provenance · "
        "Tiered approval ($1,000 default) · Jev gate can only tighten · Sagas · Audit with crypto-shredding",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Proposed calls from Orchestration (Comp 2): tool, arguments,\n"
                 "  checkpoint + tool-call IDs, user, tier, on-behalf-of token (Comp 1)\n"
                 "• Approval signals from HITL (13) via Temporal\n"
                 "• Tool definitions from developers · thresholds + screening rules (7)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Results (typed fields + reference + summary) → Orchestration / Memory (4)\n"
                 "• Approval requests with dry-run preview → HITL (13)\n"
                 "• Audit records → Data (8) · errors, breaker state → Observability (10)\n"
                 "• Allow-listed structured fields → Memory facts (MS-D16)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Planning (Comp 2) · approval queues + UI (13) · policy + screening engine (7)\n"
                   "• Platform rate limits (11) · waits + timers (Temporal) · tokens (1)\n"
                   "• Audit storage + keys (8) · the external systems\n"
                   "• Telling the user (1 / 12)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Flow A: read ────────────────────────────────────────────────────
    y += h + 40
    fa_y = y
    r1_y = fa_y + 45
    h1 = row(r1_y, [
        ("a0", "NOT OWNED →\nOrchestration proposes a step\n(user, tier, on-behalf-of token)", None, True),
        ("a1", "① Shortlist (TA-D1)\n• Code: only tools this tier + role may use\n• Jev ranks the registry → shortlist\n• Low confidence → human (Q3)", "yellow", False),
        ("a2", "② Pick + Arguments (ADP-05, TA-D3)\n• Jev Choice: tool + closed-set args\n• IDs / amounts / environment must come\n  from the user or allow-listed fields (D13)", "yellow", False),
        ("a3", "③ Validate + Gate (TA-D5, D6)\n• Pydantic schema · read tier = allow\n• Jev allow / ask / deny: can only tighten\n• 'Serves the request?' Noul", "orange", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    r2_y = r1_y + h1 + 70
    h2 = row(r2_y, [
        ("a7", "⑦ Audit (TA-D12, D15)\n• Append-only record per call\n• Personal fields encrypted per user\n• Erasure deletes the key", "light-violet", False),
        ("a6", "⑥ Screen Output (TA-D9)\n• Comp 7 engine before the LLM reads it\n• Size cap · stored by reference (MS-D7)\n• Summary inline", "light-red", False),
        ("a5", "⑤ Call (TA-D4, D10)\n• On-behalf-of token, or scoped service\n  account + agent-side user check\n• Retry reads with backoff · breaker", "light-blue", False),
        ("a4", "④ Billing Worker Pool (TA-D11, Q2)\n• Temporal activity, billing task queue\n• Outbound allow-list (no SSRF)\n• get_invoice_breakdown(INV-9821)", "light-blue", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    fa_h = (r2_y + h2 + 25) - fa_y
    pb.frame_behind("flowA", "FLOW A · READ: get_invoice_breakdown(invoice_id=\"INV-9821\")  (Sarah @ acme-corp, T2)",
                    START_X, fa_y, TOTAL_W, fa_h, "green")
    for i, (s, t) in enumerate([("a0", "a1"), ("a1", "a2"), ("a2", "a3")]):
        connect(f"a{i}", s, t, color="blue")
    connect("turn", "a3", "a4", fa="B", ta="T", color="grey", label="allowed")
    for i, (s, t) in enumerate([("a4", "a5"), ("a5", "a6"), ("a6", "a7")]):
        connect(f"b{i}", s, t, fa="L", ta="R", color="green")

    # ── Flow B: write with approval ─────────────────────────────────────
    y = fa_y + fa_h + 40
    fb_y = y
    hb = row(fb_y + 45, [
        ("c1", "① Propose (TA-D3)\n• apply_credit_memo(INV-9821, 12400)\n• Amount traced to the Flow A result", "light-blue", False),
        ("c2", "② Tier (TA-D5, D14, Q1)\n• Per call ≥ tenant threshold\n  (default $1,000) → human approval\n• Jev gate may only tighten (D6)", "orange", False),
        ("c3", "③ Preview (TA-D7)\n• Dry run if the API supports it\n• Else arguments + fresh state read\n• Goes on the approval card", "light-violet", False),
        ("c4", "④ Wait + Resume (MS-D9, D18)\n• Checkpoint before the call\n• Temporal waits for approval (13)\n• > 1 h: re-fetch, re-check", "light-blue", False),
        ("c5", "⑤ Execute + Verify\n• Idempotency key = checkpoint + call ID\n• Checkpoint after · read back result\n• Reply quotes the verified result (12)", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("c1", "c2"), ("c2", "c3"), ("c3", "c4"), ("c4", "c5")]):
        connect(f"c{i}", s, t, color="violet")
    fb_h = hb + 70
    pb.frame_behind("flowB", "FLOW B · WRITE WITH APPROVAL: $12,400 credit memo",
                    START_X, fb_y, TOTAL_W, fb_h, "violet")

    # ── Flow C + D: failure, rollback, onboarding ───────────────────────
    y = fb_y + fb_h + 40
    fc_y = y
    hc = row(fc_y + 45, [
        ("d1", "① CRM 504 (TA-D10)\n• Read → retry, backoff + jitter\n• Breaker opens after repeats", "light-blue", False),
        ("d2", "② SAP 401 (TA-D10)\n• Auth error: no retry\n• Normalized for the agent\n• Token alert → Comp 10", "light-blue", False),
        ("d3", "③ Step failed (ADP-04, ADP-05-Q1)\n• Jev Noul: did it succeed? → no\n• Reflexion, max 2 → human", "yellow", False),
        ("d4", "④ Saga rollback (TA-D8, D17, D18)\n• Temporal runs compensations in reverse\n• Compensations are idempotent tools\n• Failed undo → human · no-undo steps last + approved", "orange", False),
        ("d5", "ONBOARDING (Flow D, TA-D2, D16)\n• Python function + Pydantic schema\n• Risk class: author + second reviewer\n• Risky tools need approval until reviewed", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("d1", "d2"), ("d2", "d3"), ("d3", "d4")]):
        connect(f"d{i}", s, t, color="blue")
    fc_h = hc + 70
    pb.frame_behind("flowC", "FLOW C · FAILURE & ROLLBACK (CRM 504, expired SAP token, multi-system write fails midway)  +  FLOW D · ONBOARDING",
                    START_X, fc_y, TOTAL_W, fc_h, "blue")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = fc_y + fc_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "TOOL REGISTRY\nCatalog: owner, risk class, scopes, flags.\n\n✔ D1 Jev shortlist per turn\n✔ D2 Plain Python, no MCP\n✔ D16 Reviewed risk class", "light-green", False),
        ("s2", "TOOL SCHEMAS\nTyped inputs / outputs, closed sets.\n\n✔ D3 Argument provenance\n✔ D13 Allow-listed fields only", "light-green", False),
        ("s3", "TOOL INVOCATION\nCredentials, keys, isolation, sagas.\n\n✔ D4 On-behalf-of or scoped account\n✔ D8 Temporal sagas · D17 safe undo\n✔ D9 Screen output · D11 pool per system\n✔ D18 No-undo steps last", "light-green", False),
        ("s4", "EXTERNAL SYSTEMS\nAdapters: auth, limits, errors.\n\n✔ Q2 Temporal task queue per system\n✔ D11 Outbound allow-list", "light-green", False),
        ("s5", "ACTION VALIDATION\nSchema, permission, tier, preview.\n\n✔ D5 Tiered approval (Q1: $1,000)\n✔ D6 Jev gate, only tightens (Q4)\n✔ D7 Dry run where supported\n✔ D14 Per-call threshold", "light-green", False),
        ("s6", "ERROR HANDLING + AUDIT\nClassify, retry, normalize, record.\n\n✔ D10 Retry reads + idempotent writes\n✔ D12 Audit + before/after state\n✔ D15 Crypto-shredding", "light-green", False),
    ], "light-green")

    # ── Jev placements ──────────────────────────────────────────────────
    y += hs + 30
    hj = row(y, [
        ("jev", "JEV IN THIS COMPONENT (ADP-05, masked input only)\n"
                "• Tool shortlist: Choice ranking over allowed tools (D1) · uses 1, 4\n"
                "• Tool pick + closed-set args: Choice (ADP-05) · use 3\n"
                "• Gate: allow / ask / deny + 'serves the request?' (D6) · uses 3, 9\n"
                "• Step success: Noul (ADP-05-Q1) · uses 6, 9", "yellow", False),
        ("nojev", "NOT JEV\n"
                  "• Thresholds, amounts, dates: code\n"
                  "• Retries, breakers, idempotency, HTTP error classes: code\n"
                  "• Output screening: Comp 7 engine", "light-red", False),
    ], "yellow")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hj + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Arguments fail validation → FIXED for closed sets (Jev + Pydantic)\n"
              "• KK2 Agent claims a refund that never ran → MITIGATED (read back; reply check → Comp 12)\n"
              "• KK3 Expired token → every call 401 → MITIGATED (no retry; alert → Comp 10)\n"
              "• KK4 Downstream 500 / 504 / 14 s → MITIGATED (retry + breaker + pool per system)\n"
              "• KK5 Retried write runs twice → FIXED if tools honour idempotency keys\n"
              "• KK6 Agent-side user check wrong → OWNED (tests → Comp 9)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Right tool missing from shortlist → MITIGATED (low confidence → human)\n"
              "• KU2 Jev gate asks / denies too often → OWNED (calibrate per route)\n"
              "• KU3 Output larger than expected → MITIGATED (size cap, by reference)\n"
              "• KU4 Many tools have no dry run → MITIGATED (fresh state read on the card)\n"
              "• KU5 Undo steps that can't undo → MITIGATED (D18 last + approved)",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Defaulting to production → FIXED (D3 environment from the user)\n"
              "• UK2 Off-purpose reads (salary tables) → MITIGATED (Jev 'serves the request?')\n"
              "• UK3 Irreversible tool marked low-risk → MITIGATED (D16 review)\n"
              "• UK4 Change freezes nobody encoded → OWNED → Comp 7 policy",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Shortlist steered to a powerful tool → MITIGATED (code filter first + gate)\n"
              "• UU2 Planted value in tool text fills an argument → MITIGATED (D13 allow-listed fields)\n"
              "• UU3 Undo runs twice → FIXED (D17 idempotent compensations)\n"
              "• UU4 $12,400 split into sub-threshold calls → OWNED, accepted (D14; audit + alerts)\n"
              "• UU5 Audit keeps erased personal data → FIXED (D15 crypto-shredding)",
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
                "✔ D1 Jev shortlist · D2 plain Python · D3 argument provenance\n"
                "✔ D4 on-behalf-of or scoped account · D5 tiered approval · D6 Jev gate\n"
                "✔ D7 dry run · D8 Temporal sagas · D9 screen output · D10 safe retries\n"
                "✔ D11 pool per system · D12 audit + state · D13 allow-listed fields\n"
                "✔ D14 per-call threshold · D15 crypto-shredding · D16 reviewed risk class\n"
                "✔ D17 safe undo · D18 no-undo steps last\n"
                "✔ Q1 $1,000 default · Q2 task queue per system · Q3 → human · Q4 ask user / specialist", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 2 / 4: track where argument values came from (D3)\n"
                "Comp 7: authorization policy (KK6), screening engine (D9), change freezes (UK4)\n"
                "Comp 8: audit store + per-user keys (D12, D15) · Comp 9: shortlist + auth tests\n"
                "Comp 10: token + sub-threshold alerts · Comp 12: quote verified results\n"
                "Comp 13: approval queue, 'ask' routing, shortlist hand-off\n\n"
                "OWNED RISKS TO WATCH\n"
                "KK6 agent-side check · KU2 gate friction · UU4 threshold splitting\n\n"
                "Full reasoning: checkpoint.md §8", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §8.6 – §8.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")

    return pb.records("LLD - [4] Tools & Actions", "a6")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
