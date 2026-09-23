"""
Generate LLD page for Component [1/15]: User & Application.

Materializes checkpoint.md §5 (loop step 11): trajectory diagrams (Flows A/B/C),
boundary, one card per sub-component (mechanic + status), the Known/Unknown
failure grid with step-9 effects, and a decision-log summary.

Only the page `page:lld_user_app` is replaced; every other page is left untouched.
"""

import json
import math
import os

from generate_lld_page import _Idx, arrow, box, frame

PID = "page:lld_user_app"
TOTAL_W = 2600
START_X = 80
GAP = 30


def est_h(text, w, line_h=25, pad=26):
    """Estimate box height for size 's' sans text so labels don't overflow."""
    usable = max(w - 30, 50)
    lines = sum(max(1, math.ceil(len(line) * 8.8 / usable)) for line in text.split("\n"))
    return pad + lines * line_h


def build_records():
    idx = _Idx(500)
    R = []
    b = {}

    def add(nid, text, x, y, w, h, color, fill="semi", ext=False, **kw):
        b[nid] = (x, y, w, h)
        if ext:
            R.append(frame(f"shape:ua_{nid}", text, x, y, w, h, "grey", idx, page_id=PID))
        else:
            R.append(box(f"shape:ua_{nid}", text, x, y, w, h, color, fill, idx, page_id=PID, **kw))

    def anchor(nid, side):
        x, y, w, h = b[nid]
        return {"R": (x + w, y + h / 2), "L": (x, y + h / 2),
                "T": (x + w / 2, y), "B": (x + w / 2, y + h)}[side]

    def connect(aid, a, z, fa="R", ta="L", label="", color="black", bend=0, size="s"):
        x1, y1 = anchor(a, fa)
        x2, y2 = anchor(z, ta)
        R.append(arrow(f"shape:ua_a_{aid}", x1, y1, x2, y2, label, idx,
                       bend=bend, color=color, size=size, page_id=PID))

    def row(y, items, color_default, x0=START_X, width=TOTAL_W, gap=GAP):
        """Lay out (nid, text, color|None, ext) boxes in one row with a shared height."""
        n = len(items)
        w = (width - (n - 1) * gap) / n
        h = max(est_h(t, w) for _, t, _, _ in items)
        for i, (nid, text, color, ext) in enumerate(items):
            add(nid, text, x0 + i * (w + gap), y, w, h, color or color_default, ext=ext)
        return h

    # ── Title ────────────────────────────────────────────────────────────
    add("title",
        "COMPONENT [1/15]: USER & APPLICATION\n"
        "Web channel · Decoupled API (POST 202 + resumable SSE) · Tiered identity · Sessions · Typed response events",
        START_X, 40, TOTAL_W, 70, "blue", size="m", align="middle", vertical_align="middle")

    # ── Boundary ─────────────────────────────────────────────────────────
    y = 130
    h = row(y, [
        ("recv", "RECEIVES (upstream)\n"
                 "• Raw user input from the web widget (HTTPS)\n"
                 "• IdP tokens (SSO) · one-time codes (T1)\n"
                 "• On return: gated response envelope (Comp 7 / 9 / 13)\n"
                 "• Deferred outcome events from workflows (Comp 2)", "light-blue", False),
        ("hand", "HANDS OFF (downstream)\n"
                 "• InboundTurnEnvelope → Safety (7) → Orchestration (2)\n"
                 "• Identity context + on-behalf-of token (sub = user, act = agent)\n"
                 "• Rendered transcript + delivery receipts → Data (8), Observability (10)", "light-green", False),
        ("notown", "DOES NOT OWN\n"
                   "• PII masking, injection checks, output guardrails (7)\n"
                   "• Rate limiting (11) · tool permissions (5 / 7)\n"
                   "• Memory content (4) · workflow timers (2) · transcript storage (8)\n"
                   "• Confidence gate (9) · escalation decision (13)", "light-red", False),
    ], "light-blue")

    # ── Flow A: synchronous web turn ─────────────────────────────────────
    y += h + 40
    fa_y = y
    inner_x, inner_w = START_X + 30, TOTAL_W - 60
    row1_y = fa_y + 45
    h1 = row(row1_y, [
        ("a1", "① Web Widget\n• Only channel in v1 (UA-D1)\n• Sends message + turn_id", "light-blue", False),
        ("a2", "② API: POST /turns\n• 202 + turn_id (UA-D2)\n• Idempotency-Key = turn_id\n• Size / type / version checks", "light-blue", False),
        ("a3", "③ Identity\n• Validate token (24 h, UA-D9)\n• Tier: T0 anon · T1 code · T2 SSO\n• Mint on-behalf-of token", "light-violet", False),
        ("a4", "④ Sessions\n• Resolve / create session\n• Owner check: principal + tenant\n• 30 min idle / 12 h cap", "light-violet", False),
        ("a5", "⑤ Request Envelope\n• tenant · principal · tier\n• session · conversation · turn\n• content · attachment refs", "light-green", False),
        ("a6", "NOT OWNED →\nSafety (7) → Orchestration (2)\n→ Tools · Memory · RAG\n→ Output guard + Confidence gate", None, True),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    row2_y = row1_y + h1 + 70
    h2 = row(row2_y, [
        ("r4", "⑨ Widget Renders\n• Citations & action cards\n• Transcript as rendered → Data (8)", "light-blue", False),
        ("r3", "⑧ GET /events (SSE)\n• Resumable: event_id → Last-Event-ID\n• Replays missed events from the log", "light-blue", False),
        ("r2", "⑦ Render Typed Events (UA-D7)\nstatus · text_delta · citation · action_card\nhandoff · final · error\nText before final? → UA-D8 OPEN", "yellow", False),
        ("r1", "NOT OWNED ←\nGated OutboundResponseEnvelope\n(after output safety + confidence gate)", None, True),
    ], "light-blue", x0=inner_x, width=inner_w, gap=70)

    fa_h = (row2_y + h2 + 25) - fa_y
    R.insert(0, frame("shape:ua_f_flowA", "FLOW A · SYNCHRONOUS WEB TURN (Sarah @ acme-corp)",
                      START_X, fa_y, TOTAL_W, fa_h, "blue", idx, page_id=PID))

    for i, (s, t) in enumerate([("a1", "a2"), ("a2", "a3"), ("a3", "a4"), ("a4", "a5"), ("a5", "a6")]):
        connect(f"in{i}", s, t, color="blue")
    connect("turn", "a6", "r1", fa="B", ta="T", color="grey", label="final answer")
    for i, (s, t) in enumerate([("r1", "r2"), ("r2", "r3"), ("r3", "r4")]):
        connect(f"out{i}", s, t, fa="L", ta="R", color="green")

    # ── Flow B (deferred delivery) + Flow C (session lifecycle) ─────────
    y = fa_y + fa_h + 40
    fb_w = 1040
    fc_x = START_X + fb_w + 40
    fc_w = TOTAL_W - fb_w - 40
    inner_y = y + 45
    hb = row(inner_y, [
        ("b1", "NOT OWNED\nHITL approves the $12,400 credit memo hours later (Temporal signal, Comp 2 / 13)", None, True),
        ("b2", "Outbound event appended to the conversation log", "light-green", False),
        ("b3", "User online?\n• Yes → live on SSE\n• No → inbox on next visit (UA-Q2)\n• No email notice in v1", "yellow", False),
    ], "light-green", x0=START_X + 25, width=fb_w - 50, gap=60)
    connect("b12", "b1", "b2", color="green")
    connect("b23", "b2", "b3", color="green")

    hc = row(inner_y, [
        ("c1", "Resume\nReconnect with Last-Event-ID → missed events replayed", "light-blue", False),
        ("c2", "Step-up\nDownstream asks for a higher tier: T0 → T1 (code) → T2 (SSO), then the turn resumes", "light-violet", False),
        ("c3", "Expiry\n30 min idle (any authed request incl. open SSE, UA-Q3) · 12 h cap. Conversation outlives the session", "light-violet", False),
        ("c4", "Channel switch\nUA-D5 OPEN (session vs conversation vs case). Moot in web-only v1", "yellow", False),
    ], "light-blue", x0=fc_x + 25, width=fc_w - 50, gap=25)

    fbc_h = max(hb, hc) + 70
    R.insert(0, frame("shape:ua_f_flowB", "FLOW B · DEFERRED DELIVERY (HITL resolves while user is away)",
                      START_X, y, fb_w, fbc_h, "green", idx, page_id=PID))
    R.insert(0, frame("shape:ua_f_flowC", "FLOW C · SESSION LIFECYCLE (independent scenarios)",
                      fc_x, y, fc_w, fbc_h, "violet", idx, page_id=PID))

    # ── Sub-component cards ─────────────────────────────────────────────
    y += fbc_h + 40
    add("sub_hdr", "SUB-COMPONENTS · MECHANIC + STATUS", START_X, y, TOTAL_W, 45, "blue",
        size="m", align="middle", vertical_align="middle")
    y += 60
    hs = row(y, [
        ("s1", "CHANNELS / UI\nWeb widget only; renders typed events. Channel-agnostic envelope keeps later Slack / Teams / Email adapters additive.\n\n✔ UA-D1 Web-only v1: CONFIRMED", "light-green", False),
        ("s2", "API\nSubmit and receive are separate. POST /turns → 202 + turn_id; GET /events is a resumable SSE stream.\n\n✔ UA-D2 Decoupled POST + SSE: CONFIRMED", "light-green", False),
        ("s3", "IDENTITY\nValidates tokens, sets tier, issues step-up, mints on-behalf-of tokens.\n\n✔ UA-D3 Tiered T0 / T1 / T2: CONFIRMED\n✔ UA-D4 On-behalf-of tokens, T0 read-only: CONFIRMED (conditional)\n✔ UA-D9 24 h user token: CONFIRMED", "light-green", False),
        ("s4", "SESSIONS\nBinds principal ↔ session ↔ conversation. Owns the keys, not the content.\n\n✔ UA-D6 30 min idle / 12 h: CONFIRMED\n✔ UA-Q3 Open stream counts as activity\n◌ UA-D5 Scoping: OPEN → Comp 4 / 13", "yellow", False),
        ("s5", "REQUEST / RESPONSE\nBuilds the inbound envelope; renders and delivers gated responses (live or deferred).\n\n✔ UA-D7 Typed events: CONFIRMED\n✔ UA-Q2 Inbox-only deferred delivery\n◌ UA-D8 Stream vs gate: OPEN → Comp 7 / 9", "yellow", False),
    ], "light-green")

    # ── Failure grid ────────────────────────────────────────────────────
    y += hs + 40
    add("fail_hdr", "FAILURE MODES (KNOWN / UNKNOWN) · WITH STEP-9 EFFECT", START_X, y, TOTAL_W, 45, "red",
        size="m", align="middle", vertical_align="middle")
    y += 60
    q = {
        "q1": "Q1 · KNOWN KNOWNS (contract breaches)\n"
              "• KK1 Duplicate turn on client retry → FIXED (D2 idempotency)\n"
              "• KK2 Proxy timeout cuts SSE mid-answer → loss FIXED (D2 replay); gap still visible\n"
              "• KK3 Token expiry / revocation on open stream → expiry FIXED (D9); revocation + 24 h theft window OWNED\n"
              "• KK4 Reading another user's conversation by ID → MITIGATED (owner check); final model waits on D5\n"
              "• KK5 One-time code guessed / replayed → OWNED (limits → Comp 7 / 11)\n"
              "• KK6 On-behalf-of token outlives logout → MITIGATED (short-lived); revocation OWNED",
        "q2": "Q2 · KNOWN UNKNOWNS (magnitude unknown)\n"
              "• KU1 Corporate proxies hold back SSE → MITIGATED (D2); no fallback, OWNED\n"
              "• KU2 Drop-off at step-up login → MITIGATED (D3); unmeasured\n"
              "• KU3 Capacity: 12 h open streams + replay log → OWNED (Comp 11 / 8)\n"
              "• KU4 Users never return to the inbox → OWNED, accepted (Q2)\n"
              "• KU5 Answer speed while D8 is open → OWNED until Comp 7 / 9",
        "q3": "Q3 · UNKNOWN KNOWNS (tacit conventions)\n"
              "• UK1 No \"you're talking to an AI\" notice → OWNED (cheap fix)\n"
              "• UK2 Streamed text floods screen readers → MITIGATED only if renderer batches (D7)\n"
              "• UK3 Anonymous user's claimed identity trusted → FIXED for actions (D4 T0 read-only)\n"
              "• UK4 Inbox item without the original question → MITIGATED (turn_id link, D7)\n"
              "• UK5 Shared computer stays logged in 12 h → OWNED, accepted (Q3)",
        "q4": "Q4 · UNKNOWN UNKNOWNS (emergent from combined decisions)\n"
              "• UU1 Replayed approval card clicked twice (D2 × D7) → OWNED → action idempotency, Comp 5\n"
              "• UU2 T0 read-only scope creeps into enumerable lookups → OWNED → Comp 7\n"
              "• UU3 Earlier anonymous turns inherit later T2 authority → OWNED, revisit with D5\n"
              "• UU4 Renderer leaks data via model-written links / images → MITIGATED (D7) + Comp 7\n"
              "• UU5 All 12 h streams reconnect after a deploy → OWNED → Comp 11",
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
        ("dl1", "CONFIRMED\n"
                "✔ UA-D1 Web-only v1\n"
                "✔ UA-D2 POST 202 + resumable SSE\n"
                "✔ UA-D3 Tiered identity T0 / T1 / T2 + step-up\n"
                "✔ UA-D4 On-behalf-of tokens, T0 read-only (conditional)\n"
                "✔ UA-D6 30 min idle / 12 h cap\n"
                "✔ UA-D7 Typed event envelope\n"
                "✔ UA-D9 24 h user token\n"
                "✔ UA-Q2 Inbox-only deferred delivery · UA-Q3 Open stream = activity", "green", False),
        ("dl2", "OPEN (logged, not dropped)\n"
                "◌ UA-D5 Session / conversation / case → revisit at Comp 4 & 13\n"
                "◌ UA-D8 Streaming vs safety gate → revisit after Comp 7 & 9 (likely experiment)\n\n"
                "OWNED RISKS TO WATCH\n"
                "KK3 revocation · KU4 inbox never read · UK5 shared devices · UU1 replayed cards\n\n"
                "Full reasoning: checkpoint.md §5", "yellow", False),
    ], "green", x0=START_X + 20, width=TOTAL_W - 40, gap=GAP)
    R.insert(0, frame("shape:ua_f_declog", "DECISION LOG SUMMARY (checkpoint.md §5.6 – §5.10)",
                      START_X, dl_y, TOTAL_W, hd + 60, "green", idx, page_id=PID))

    # Frames were inserted at the front after being built; re-index so z-order follows list order.
    order = _Idx(500)
    for s in R:
        s["index"] = order()

    page = {"typeName": "page", "id": PID, "name": "LLD - [1] User & Application", "index": "a3", "meta": {}}
    camera = {"typeName": "camera", "id": f"camera:{PID}", "x": 0, "y": 0, "z": 0.4, "meta": {}}
    return page, camera, R


def main():
    target = "architecture.tldr"
    if not os.path.exists(target):
        print(f"Error: {target} not found!")
        return
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)

    kept = [r for r in data.get("records", [])
            if r.get("id") not in (PID, f"camera:{PID}") and r.get("parentId") != PID]
    page, camera, shapes = build_records()
    data["records"] = kept + [page, camera] + shapes

    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Generated page '{page['name']}' with {len(shapes)} shapes in {target}.")


if __name__ == "__main__":
    main()
