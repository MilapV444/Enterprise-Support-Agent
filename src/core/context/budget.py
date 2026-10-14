"""Turn and daily token budgets (FR-41 / CR-ADP-02 CR-D5).

A turn has a budget by route, with room kept for one verification cascade step; at 90 % of what is left the
agent wraps up instead of being cut off mid-sentence. A conversation past 50,000 tokens in 24 hours goes to a
human. Counting usage is the cost counter's job (CR-ADP-04); this only decides what the numbers mean.
"""

TURN_BUDGETS = {"faq": 4_000, "standard": 8_000, "complex": 16_000}
DAILY_CEILING = 50_000
WRAP_UP_AT = 0.90


def status(route, turn_tokens, day_tokens, cascade_reserve=0):
    """What to do now: "handoff", "wrap_up" or "ok", given the turn and 24-hour token counts."""
    if day_tokens >= DAILY_CEILING:
        return "handoff"
    if turn_tokens >= WRAP_UP_AT * (TURN_BUDGETS[route] - cascade_reserve):
        return "wrap_up"
    return "ok"
