"""
Generate LLD page for Component [11/15]: Cost & Resource Management.

Materializes checkpoint.md §15 (loop step 11): boundary, Flow A (one turn:
tier, cascade, budgets), the answer cache, budgets and reporting, one card per
sub-component (mechanic + status), Jev placements, the Known/Unknown failure
grid with step-9 effects (after §15.9a), and a decision-log summary.

Only the page `page:lld_cost` is replaced; every other page is left untouched.
"""

from lld_layout import PageBuilder, est_h, write_page

PID = "page:lld_cost"
TOTAL_W = 2600
START_X = 80
GAP = 30


def build_records():
    pb = PageBuilder(PID, "cr")
    add, connect = pb.add, pb.connect

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        return pb.row(y, items, color_default, x0, width, gap)

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [11/15]: COST & RESOURCE MANAGEMENT\n"
        "Jev difficulty picks the tier · Cascade on failed checks · Per-tenant answer cache · "
        "Turn + tenant budgets · Exact cost tracking · ≤ 10 % cost rise per release",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Exact usage counter (RP-D14) · estimates (OB-D13)\n"
                 "• Price tables · tenant settings (DP-D12)\n"
                 "• Quality per model / route (EV) · capacity plans (RP)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• Model tier per step → Orchestration, specialists\n"
                 "• Budget state → Orchestration, Comp 1\n"
                 "• Cost reports → tenant admins · cost targets → release gate", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• Provider failover (RP-D4) · rate limits (RP-D1)\n"
                   "• Telemetry (OB) · measuring quality (EV)\n"
                   "• What is safe to say (SG)", "light-red", False),
    ], "light-blue")

    inner_x, inner_w = START_X + 30, TOTAL_W - 60

    # ── Flow A: one turn ────────────────────────────────────────────────
    y += h + 40
    fa_y = y
    ha = row(fa_y + 45, [
        ("a1", "① Cacheable? (CR-D3)\n• Jev Noul: answerable from\n  public docs alone?\n• Sarah: no (invoice, cluster)", "yellow", False),
        ("a2", "② Pick tier (CR-D1)\n• Jev Score: difficulty\n• Self-hosted · mid-tier · frontier\n• Sarah: frontier", "yellow", False),
        ("a3", "③ Context (CR-D6)\n• Slots + provider prompt caching\n• Compress retrieved passages\n• Never dialogue, pins, delimiters", "light-blue", False),
        ("a4", "④ Cascade (CR-D2)\n• Step fails checks / low confidence\n  → rerun one tier up", "orange", False),
        ("a5", "⑤ Budgets (CR-D5, D4)\n• Turn budget by route (+1 cascade)\n• Daily per conversation\n• Wrap up or hand off at limit", "light-violet", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)
    for i, (s, t) in enumerate([("a1", "a2"), ("a2", "a3"), ("a3", "a4"), ("a4", "a5")]):
        connect(f"a{i}", s, t, color="green")
    fa_h = ha + 70
    pb.frame_behind("flowA", "FLOW A · ONE TURN (Sarah @ acme-corp: incident + billing dispute)",
                    START_X, fa_y, TOTAL_W, fa_h, "green")

    # ── Cache + budgets + reporting ─────────────────────────────────────
    y = fa_y + fa_h + 40
    fb_y = y
    hb = row(fb_y + 45, [
        ("b1", "ANSWER CACHE (Flow B, CR-D3, D14)\n• Per tenant, 7 days\n• Public-KB answers, no account data\n• Key: question + tenant + version\n  + KB index; no version questions\n• Cleared by KB updates, tombstones", "light-blue", False),
        ("b2", "TENANT BUDGET (Flow C, CR-D4)\n• Monthly, tenant setting\n• Alert at 80 %\n• 100 %: knowledge-base-only\n  answers (soft cap)", "orange", False),
        ("b3", "COST TRUTH (CR-D11, D7)\n• Exact counter × price table\n• Monthly reconciliation with\n  invoices + GPU bills\n• Reports for tenant admins", "light-violet", False),
        ("b4", "RELEASE GATE (Flow D, CR-D12)\n• Cost per resolved conversation\n• ≤ +10 % per release\n• ≤ 1.5 × first month, per route", "light-red", False),
        ("b5", "FIXED COSTS (Flow E)\n• Self-hosted tier serves easy turns\n  (CR-D9, keeps it warm)\n• Cheaper helper tiers (CR-D8)\n• Envelope keys (CR-D10, D13)", "light-green", False),
    ], "light-blue", x0=inner_x, width=inner_w, gap=40)
    fb_h = hb + 70
    pb.frame_behind("flowB", "FLOWS B–E · CACHE, BUDGETS, TRACKING, RELEASES, FIXED COSTS",
                    START_X, fb_y, TOTAL_W, fb_h, "violet")

    # ── Sub-component cards ─────────────────────────────────────────────
    y = fb_y + fb_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "TOKEN MANAGEMENT\n\n✔ D5 Turn + daily budgets\n✔ D6 Prompt caching +\n   compression", "light-green", False),
        ("s2", "MODEL SELECTION\n\n✔ D1 Jev difficulty, 3 tiers\n✔ D2 Cascade", "light-green", False),
        ("s3", "COST TRACKING\n\n✔ D7 Tenant reports\n✔ D11 Exact + reconciled", "light-green", False),
        ("s4", "COST OPTIMIZATION\n\n✔ D3, D14 Answer cache\n✔ D8 Cheaper helpers\n✔ D9 Self-hosted share\n✔ D10, D13 Envelope keys", "light-green", False),
        ("s5", "USAGE BUDGETS\n\n✔ D4 Tenant soft cap\n✔ D12 Release gate", "light-green", False),
    ], "light-green")

    # ── Jev placements ──────────────────────────────────────────────────
    y += hs + 30
    hj = row(y, [
        ("jev", "JEV IN THIS COMPONENT (masked input only)\n"
                "• Model tier: Score of difficulty (CR-D1) · use 1\n"
                "• Cache eligibility: Noul 'answerable from public docs alone?' (CR-D3) · use 4", "yellow", False),
        ("nojev", "NOT JEV\n"
                  "• Budgets, prices, percentages, ceilings: code\n"
                  "• Answers themselves: LLM tiers", "light-red", False),
    ], "yellow")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hj + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Reply cut off by a token ceiling → FIXED (wrap up / hand off)\n"
              "• KK2 Cheap model fails the reasoning → MITIGATED (cascade)\n"
              "• KK3 Price table out of date → MITIGATED (monthly reconciliation)",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Difficulty-score accuracy → MITIGATED (EV-D9)\n"
              "• KU2 Cache hit rate → OWNED (measure after launch)\n"
              "• KU3 Self-hosted quality on its share → MITIGATED (EV baseline)",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 Cached answer for the wrong version → MITIGATED (D14 key)\n"
              "• UK2 Silent service reduction at the cap → MITIGATED (80 % alert)",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Deleted keys survive in backups → MITIGATED (D13, ≤ 1 day)\n"
              "• UU2 Compression drops a fact → MITIGATED (never dialogue / pins)\n"
              "• UU3 Cascade hits the turn budget → MITIGATED (room for one step)\n"
              "• UU4 Users game the difficulty score → MITIGATED (budgets)",
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
        ("dl1", "CONFIRMED (14 decisions + 4 follow-ups, none open)\n"
                "✔ D1 Jev tier, 3 tiers · D2 cascade · D3 per-tenant cache, 7 days\n"
                "✔ D4 tenant soft cap · D5 turn + daily budgets · D6 caching + compression\n"
                "✔ D7 tenant reports · D8 cheaper helpers · D9 self-hosted share\n"
                "✔ D10 envelope keys (revises DP-D4) · D11 exact cost · D12 release gate\n"
                "✔ D13 key store, 1-day backups · D14 versioned cache key", "green", False),
        ("dl2", "HAND-OFFS TO OTHER COMPONENTS\n"
                "Comp 1: budget alerts, soft-cap banner, usage reports UI\n"
                "Comp 8: key store, cache store · Comp 9: baselines per tier, compression\n"
                "Comp 10: hit rate, tier mix, cascade rate · Comp 11: key store in drills\n\n"
                "OWNED RISK TO WATCH\n"
                "KU2 cache hit rate\n\n"
                "Full reasoning: checkpoint.md §15", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    pb.frame_behind("declog", "DECISION LOG SUMMARY (checkpoint.md §15.6 – §15.10)",
                    START_X, dl_y, TOTAL_W, hd + 60, "green")

    return pb.records("LLD - [11] Cost & Resource Management", "aD")


def main():
    write_page(*build_records())


if __name__ == "__main__":
    main()
