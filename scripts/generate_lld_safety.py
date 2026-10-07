"""
Generate LLD page for Component [6/15]: Safety, Security & Governance.

Materializes checkpoint.md §10 (loop step 11): boundary, Flow A (inbound
message), Flow B (untrusted content), Flow C (outbound reply), Flow D
(authorization) with Flow E (governance), one card per sub-component
(mechanic + status), a Jev note, the Known/Unknown failure grid with step-9
effects (after §10.9a), and a decision-log summary.

Only the page `page:lld_safety` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, add_adp_section, est_h, write_page

PID = "page:lld_safety"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "sg")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [6/15]: SAFETY, SECURITY & GOVERNANCE\n"
        "Screening + spotlighting · Llama Guard 3 + injection classifier · Pass / review / block · "
        "PII token vault · Cedar policies · Decision audit + 'why' view · Human always available",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• User messages (Comp 1) · retrieved passages (3) · tool outputs (5)\n"
                 "• Conversation reads by specialists (6) · draft replies (coordinator)\n"
                 "• Authorization questions from Tools, Knowledge, Memory\n"
                 "• Erasure and retention requests (8 / back office)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Screened, tokenized envelopes → Orchestration\n"
                 "• Verdicts on passages / tool outputs → Knowledge, Tools\n"
                 "• Allow / deny → Tools, Knowledge, Memory · replies → Delivery (1)\n"
                 "• Review-band cases → HITL (13) · decision records → Data (8), Obs (10)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Answer grounding / confidence boundaries (13, measured by 9)\n"
                   "• Executing erasure + TTLs (4 / 8) · storing audit, vault, archive (8)\n"
                   "• Rate limits incl. OTP attempts (11) · approval queues (13)\n"
                   "• Token issuance (1) · tool execution (5)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Flow A: inbound message ─────────────────────────────────────────
    y += h + 40
    fa_y = y
    r1_y = fa_y + 45
    h1 = row(r1_y, [
        ("a0", "NOT OWNED →\nUser message arrives\n(Comp 1, verified identity)", None, True),
        ("a1", "① Normalize\n• Unicode NFKC + confusables\n• Invisible characters stripped\n• Size limit", "light-blue", False),
        ("a2", "② Tokenize PII (SG-D4, D5)\n• Custom recognizers\n• Technical IDs never masked\n• Global deterministic tokens → vault", "light-violet", False),
        ("a3", "③ Screen (SG-D2, D3)\n• Llama Guard 3: hazards, abuse\n• Injection classifier (not Jev)\n• Pass / review / block per source", "orange", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    r2_y = r1_y + h1 + 70
    h2 = row(r2_y, [
        ("a6", "NOT OWNED ←\nOrchestration: triage (Jev),\ndelegation, tools", None, True),
        ("a5", "⑤ Pass → envelope\n• Models see tokens only\n• Vault down: tokens stay,\n  PII-needing tools blocked (D18)", "light-green", False),
        ("a4", "④ Review / block\n• Review: read-only turn or human\n• Block: safe refusal, logged\n• Hostility: persona only (D7)", "light-red", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    fa_h = (r2_y + h2 + 25) - fa_y
    pb.frame_behind("flowA", "FLOW A · INBOUND MESSAGE (Sarah @ acme-corp, T2)",
                    START_X, fa_y, TOTAL_W, fa_h, "green")
    for i, (s, t) in enumerate([("a0", "a1"), ("a1", "a2"), ("a2", "a3")]):
        connect(f"a{i}", s, t, color="blue")
    connect("band", "a3", "a4", fa="B", ta="T", color="grey", label="verdict")
    for i, (s, t) in enumerate([("a4", "a5"), ("a5", "a6")]):
        connect(f"b{i}", s, t, fa="L", ta="R", color="green")

    # ── Flow B + C: untrusted content, outbound reply ───────────────────
    y = fa_y + fa_h + 40
    fb_y = y
    hb = row(fb_y + 45, [
        ("c1", "UNTRUSTED CONTENT (Flow B)\n• Passages (KR-D14), tool outputs (TA-D9),\n  conversation reads\n• Same screening + bands", "light-blue", False),
        ("c2", "Spotlighting (SG-D1)\n• Untrusted text fenced + marked as data\n• No quarantined LLM\n• Backstop: TA-D3, D11, MA-D9", "orange", False),
        ("c3", "OUTBOUND REPLY (Flow C)\n• Leakage: PII, secrets, system prompt\n• URLs / markdown sanitized (D6)", "light-violet", False),
        ("c4", "Promise check (SG-D15)\n• Commitment phrases need a\n  verified action, else one rewrite\n• No tone check (accepted)", "yellow", False),
        ("c5", "Deliver (Comp 1)\n• Tokens restored in the reply\n• Redirect check: Jev (MA-D13)\n• Streaming vs. gate: UA-D8 open", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("c1", "c2"), ("c3", "c4"), ("c4", "c5")]):
        connect(f"c{i}", s, t, color="violet")
    fb_h = hb + 70
    pb.frame_behind("flowB", "FLOW B · UNTRUSTED CONTENT INSIDE THE LOOP  +  FLOW C · OUTBOUND REPLY",
                    START_X, fb_y, TOTAL_W, fb_h, "violet")

    # ── Flow D + E: authorization, governance ───────────────────────────
    y = fb_y + fb_h + 40
    fc_y = y
    hc = row(fc_y + 45, [
        ("d1", "① Policy engine: Cedar (SG-D8)\n• Called by Tools, Knowledge, Memory\n• Versioned, tested policies\n• Down: writes denied, reads cached (D17)", "light-blue", False),
        ("d2", "② Rules it holds\n• Service-account user checks (TA-D4)\n• Tickets: author + support / admin (D9)\n• Blackout windows → approval (D10)", "orange", False),
        ("d3", "③ PII restore (SG-D16)\n• Only into needs_pii tool fields\n• Other fields keep the token", "light-violet", False),
        ("d4", "GOVERNANCE (Flow E)\n• Every decision recorded + versions (D13)\n• 'Why' view: users see reasons + checks\n• AI disclosure, human always (D14)", "light-green", False),
        ("d5", "RETENTION + PROVIDERS\n• Transcripts: legal archive, 2 years (D12)\n• Human review: closure, rejection,\n  contract changes (D14)\n• Standard API terms; tokens only (D11)", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("d1", "d2"), ("d2", "d3")]):
        connect(f"d{i}", s, t, color="blue")
    fc_h = hc + 70
    pb.frame_behind("flowC", "FLOW D · AUTHORIZATION  +  FLOW E · GOVERNANCE",
                    START_X, fc_y, TOTAL_W, fc_h, "blue")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = fc_y + fc_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "INPUT SAFETY\nScreen everything entering a prompt.\n\n✔ D1 Screening + spotlighting\n✔ D2 Llama Guard 3 + injection clf.\n✔ D3 Pass / review / block\n✔ D7 Hostility: persona only", "light-green", False),
        ("s2", "OUTPUT SAFETY\nCheck the reply before delivery.\n\n✔ D6 Leakage + URL / markdown\n✔ D15 Rule-based promise check", "light-green", False),
        ("s3", "AUTHORIZATION\nWho may see or do what.\n\n✔ D8 Cedar policy engine\n✔ D9 Ticket visibility by role\n✔ D17 Fail closed for writes", "light-green", False),
        ("s4", "PRIVACY / ISOLATION\nPII, providers, retention.\n\n✔ D4 Token vault · D5 global tokens\n✔ D11 Standard terms · D12 2 years\n✔ D16 needs_pii restore · D18 degrade", "light-green", False),
        ("s5", "TOOL PERMISSIONS\nPolicy side of tool access.\n\n✔ D10 Blackout windows\n(allow-lists: TA-D1, MA-D9)", "light-green", False),
        ("s6", "AUDIT / GOVERNANCE\nRecords, disclosure, rights.\n\n✔ D13 Decisions + 'why' view\n✔ D14 Disclosure + human", "light-green", False),
    ], "light-green")

    # ── Jev note ────────────────────────────────────────────────────────
    y += hs + 30
    hj = row(y, [
        ("jev", "JEV IN THIS COMPONENT\n"
                "• Not used for screening, reply checks or hostility (user choice: SG-D2, D6, D7)\n"
                "  → resolves ADP-05-Q4 'Comp 7 guardrails' as not Jev\n"
                "• Redirect check on the reply stays (MA-D13, owned by Multi-Agent)", "yellow", False),
        ("nojev", "DEDICATED ENGINES / CODE\n"
                  "• Screening: Llama Guard 3 + injection classifier\n"
                  "• Policy: Cedar · PII: recognizers + vault\n"
                  "• Blackout windows: date / time math in code", "light-red", False),
    ], "yellow")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hj + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 PII regex misses spaced SSNs → MITIGATED (custom recognizers)\n"
              "• KK2 Score 0.49 vs. 0.50 → MITIGATED (review band)\n"
              "• KK3 Homoglyph / zero-width bypass → MITIGATED (normalization)\n"
              "• KK4 Vault down → MITIGATED (tokens stay, PII tools blocked)\n"
              "• KK5 Policy bug → MITIGATED (versioned, tested Cedar policies)\n"
              "• KK6 System prompt leaks → MITIGATED (leakage check)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Classifier accuracy on support text → OWNED (Comp 9)\n"
              "• KU2 Screening latency per turn → OWNED (Comp 11)\n"
              "• KU3 Over- / under-masking → MITIGATED (ID allow-list)\n"
              "• KU4 Blackout windows misconfigured → OWNED (Comp 1 UI)",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Callous tone after data loss → OWNED, accepted (no tone check)\n"
              "• UK2 Unbacked promises (Moffatt) → MITIGATED (D15 promise check)\n"
              "• UK3 Hostile customer, standard flow → MITIGATED (human always)\n"
              "• UK4 Admins see all tenant tickets → OWNED, accepted",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Global tokens link people across tenants → OWNED, accepted\n"
              "• UU2 Token restored into an exfiltration field → MITIGATED (D16 needs_pii)\n"
              "• UU3 'Why' view helps attackers → MITIGATED (users: reasons only)\n"
              "• UU4 Vendor copies outlive erasure → MITIGATED (tokens, no PII)\n"
              "• UU5 Policy engine outage → MITIGATED (D17)",
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
        ("dl1", "CONFIRMED (18 decisions + 5 follow-ups, none open)\n"
                "✔ D1 screening + spotlighting · D2 Llama Guard 3 + injection clf. · D3 bands\n"
                "✔ D4 token vault · D5 global deterministic tokens · D6 leakage + URLs\n"
                "✔ D7 persona only · D8 Cedar · D9 tickets by role · D10 blackout windows\n"
                "✔ D11 standard terms · D12 2-year archive · D13 decisions + 'why'\n"
                "✔ D14 disclosure + human · D15 promise check · D16 needs_pii restore\n"
                "✔ D17 writes fail closed · D18 vault down: degrade", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 1: disclosure, 'talk to a human', 'why' view, blackout UI\n"
                "Comp 3: ticket author field + role filter; global tokens at ingestion\n"
                "Comp 5: needs_pii flag, blackout rule, significant-effect list\n"
                "Comp 8: vault, 2-year archive, decision records · Comp 9: classifier tests\n"
                "Comp 11: screening latency, vault + Cedar availability · Comp 13: reviews\n\n"
                "OWNED RISKS TO WATCH\n"
                "KU1 classifier accuracy · KU2 latency · UK1 tone · UU1 cross-tenant tokens\n\n"
                "Full reasoning: checkpoint.md §10", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §10.6 – §10.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")


    # ── Architectural Decision Points (from the checkpoint.md decision log) ──
    add_adp_section(pb, "SG", START_X, TOTAL_W)

    return pb.records("LLD - [6] Safety, Security & Governance", "a8")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
