"""
Generate LLD page for Component [7/15]: Data & Persistence.

Materializes checkpoint.md §11 (loop step 11): boundary, the store map per
region, Flow A (writes during one turn), Flow B (erasure) with Flows C / D
(tenant offboarding, restore), one card per sub-component (mechanic + status),
the Known/Unknown failure grid with step-9 effects (after §11.9a), and a
decision-log summary.

Only the page `page:lld_data` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, est_h, write_page

PID = "page:lld_data"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "dp")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [7/15]: DATA & PERSISTENCE\n"
        "US + EU regions · Postgres with row-level security · Qdrant for Knowledge · Isolated token vault · "
        "Per-user data keys (envelope) · Erasure as a Temporal workflow · 35-day backups",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Writes + reads from every component through its own data model\n"
                 "• Erasure and tenant-offboarding requests\n"
                 "• TTL rules (MS-D10), retention rules (SG-D12)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Durable storage, backups, restores, encryption keys\n"
                 "• Deletion fan-out to Knowledge (Qdrant), Cache (12)\n"
                 "• Records for Observability (10), Evaluation (9)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• What is stored and when it expires (owners + Comp 7 policy)\n"
                   "• Index building + retrieval (3) · Temporal internals\n"
                   "• Capacity targets (11) · semantic cache (12)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Store map (per region) ──────────────────────────────────────────
    y += h + 40
    sm_y = y
    hm = row(sm_y + 45, [
        ("m1", "POSTGRES (pool + forced RLS, DP-D2)\n• Turns, idempotency, cases\n• LangGraph checkpoints, memory, facts\n• Tenant settings (DP-D12)", "light-blue", False),
        ("m2", "POSTGRES: APPEND-ONLY (DP-D3, D8)\n• Tool audit + decision records\n• Transcript archive, 2 years\n• Event log, 7-day replay (DP-D7)", "light-violet", False),
        ("m3", "TOKEN VAULT (DP-D5, Q2)\n• Separate, isolated database\n• Vault per region\n• One token key for all regions", "orange", False),
        ("m4", "QDRANT (DP-D1, Q1)\n• Public collection\n• Per-tenant private collections\n• Hybrid dense + sparse", "light-green", False),
        ("m5", "OBJECT STORAGE + KMS\n• Working-memory blobs (MS-D7)\n• Raw snapshots per batch (DP-D11)\n• Key store: per-user data keys,\n  1-day backups (DP-D4, CR-D13)", "yellow", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=40)
    sm_h = hm + 70
    pb.frame_behind("stores", "STORES · ONE SET PER REGION (US, EU) · TENANT PINNED TO ONE REGION (DP-D10)",
                    START_X, sm_y, TOTAL_W, sm_h, "blue")

    # ── Flow A: writes in one turn ──────────────────────────────────────
    y = sm_y + sm_h + 40
    fa_y = y
    ha = row(fa_y + 45, [
        ("a1", "① Turn submitted\n• Turn row + idempotency key\n• Tenant set from the verified token", "light-blue", False),
        ("a2", "② Each graph node\n• LangGraph checkpoint\n• Before + after side-effecting tools\n• Ledger → blob by reference", "light-blue", False),
        ("a3", "③ Each tool call / decision\n• Append-only audit record\n• Decision record (Jev, screening, policy)\n• Personal fields: user's KMS key", "light-violet", False),
        ("a4", "④ Each reply event\n• Outbound event log (SSE replay)\n• Conversation memory\n• Transcript → archive", "light-green", False),
        ("a5", "⑤ Changes to others (DP-D6)\n• Direct writes, no event bus\n• Deletions: Temporal workflow\n  (Flow B)", "orange", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("a1", "a2"), ("a2", "a3"), ("a3", "a4"), ("a4", "a5")]):
        connect(f"a{i}", s, t, color="green")
    fa_h = ha + 70
    pb.frame_behind("flowA", "FLOW A · WRITES DURING ONE TURN (Sarah @ acme-corp, case INV-9821, EU region)",
                    START_X, fa_y, TOTAL_W, fa_h, "green")

    # ── Flow B + C + D ──────────────────────────────────────────────────
    y = fa_y + fa_h + 40
    fb_y = y
    hb = row(fb_y + 45, [
        ("b1", "① Erasure request\n• Starts a Temporal workflow\n  (DP-D13)", "light-blue", False),
        ("b2", "② Fan-out with retries\n• Every store in the MS-D14 inventory\n• Qdrant, semantic cache, vault\n• Completion check", "orange", False),
        ("b3", "③ Keys + snapshots\n• Delete Sarah's data key (DP-D4)\n• Remove her items from every\n  raw snapshot (DP-D15)", "light-violet", False),
        ("b4", "④ What remains\n• Transcript archive, 2 years (SG-D12)\n• Backups up to 35 days (DP-D9)\n• Audit rows, unreadable fields", "yellow", False),
        ("b5", "OFFBOARDING + RESTORE\n• Tenant: delete by tenant_id, private\n  collection, all users' keys\n• Restore can bring back erased data\n  (accepted, DP-D14)", "light-red", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("b1", "b2"), ("b2", "b3"), ("b3", "b4")]):
        connect(f"b{i}", s, t, color="violet")
    fb_h = hb + 70
    pb.frame_behind("flowB", "FLOW B · SARAH ASKS TO BE ERASED  +  FLOW C · TENANT OFFBOARDING  +  FLOW D · RESTORE",
                    START_X, fb_y, TOTAL_W, fb_h, "violet")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = fb_y + fb_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "OPERATIONAL DATA\nTenants, users, settings, turns.\n\n✔ D12 Platform in code,\n   tenant settings in DB", "light-green", False),
        ("s2", "SQL / DATABASE\nEngines, isolation, regions, backups.\n\n✔ D1 Postgres + Qdrant\n✔ D2 Pool + forced RLS\n✔ D9 35-day backups · D14 restore\n✔ D10 US + EU regions", "light-green", False),
        ("s3", "DATA MODELS\nShared schemas, keys, encryption.\n\n✔ D4 Envelope encryption\n   (revised by CR-D10)\n✔ D5 Isolated token vault", "light-green", False),
        ("s4", "AGENT / CONVERSATION\nEvent log, memory, archive.\n\n✔ D7 7-day replay window\n✔ D8 Archive in Postgres, 2 years", "light-green", False),
        ("s5", "KNOWLEDGE DATA\nRaw sources + deletion list.\n\n✔ D11 Snapshot per batch\n✔ D15 Erased items removed", "light-green", False),
        ("s6", "AUDIT / EVENTS\nAudit, decisions, change events.\n\n✔ D3 Append-only Postgres\n✔ D6 Direct writes\n✔ D13 Deletion as a workflow", "light-green", False),
    ], "light-green")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hs + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT  ·  No Jev use in this component", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Table without RLS reads across tenants → MITIGATED (forced RLS; CI check → Comp 14)\n"
              "• KK2 Migration breaks another component → OWNED (Comp 14)\n"
              "• KK3 Untested backups fail to restore → OWNED (drills → Comp 11)\n"
              "• KK4 Postgres and Qdrant disagree → MITIGATED (deletion workflow)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 KMS cost per user → FIXED (envelope encryption, CR-D10)\n"
              "• KU2 Postgres write load per turn → OWNED (Comp 11)\n"
              "• KU3 Raw snapshot growth → OWNED (Comp 12)",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Audit not tamper-evident → OWNED, accepted\n"
              "• UK2 Contracts promise deletion incl. backups → MITIGATED (35 days, documented)",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Lost deletion messages → FIXED (D13 Temporal workflow)\n"
              "• UU2 Restore brings back erased data → OWNED, accepted (D14)\n"
              "• UU3 Erased content in old snapshots → FIXED (D15)\n"
              "• UU4 Global tokens vs. regions → FIXED (shared key, vault per region)",
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
                "✔ D1 Postgres + Qdrant · D2 pool + forced RLS · D3 append-only audit\n"
                "✔ D4 envelope keys (revised) · D5 isolated vault · D6 direct writes\n"
                "✔ D7 7-day replay · D8 archive in Postgres · D9 35-day backups\n"
                "✔ D10 US + EU, shared token key · D11 snapshots per batch\n"
                "✔ D12 settings split · D13 deletion workflow · D14 restore accepted\n"
                "✔ D15 erased items removed from snapshots", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 11: restore drills, write load, regional failover, token-key custody\n"
                "Comp 12: KMS per-user key cost, snapshot storage growth\n"
                "Comp 14: CI check for forced RLS, migration contract tests\n"
                "Legal / contracts: 35-day backup wording\n\n"
                "OWNED RISKS TO WATCH\n"
                "KU1 KMS cost · UK1 audit not tamper-evident · UU2 restore resurrects data\n\n"
                "Full reasoning: checkpoint.md §11", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §11.6 – §11.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")

    return pb.records("LLD - [7] Data & Persistence", "a9")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
