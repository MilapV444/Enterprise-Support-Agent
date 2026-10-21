"""AI disclosure and the always-available human (FR-34 / SG-ADP-05: SG-D14; EU AI Act Art. 50, GDPR Art. 22).

disclose() stamps every customer-facing message with the disclosure and the "talk to a human" action, so no
reply path can drop either. The web chat shows the same sentence as a persistent banner.
"""

DISCLOSURE = "You are chatting with an AI assistant. A person can take over at any time."
TALK_TO_HUMAN = {"id": "talk_to_human", "label": "Talk to a human"}


def disclose(message):
    actions = [action for action in message.get("actions", []) if action.get("id") != TALK_TO_HUMAN["id"]]
    return {**message, "ai_generated": True, "disclosure": DISCLOSURE, "actions": [*actions, TALK_TO_HUMAN]}
