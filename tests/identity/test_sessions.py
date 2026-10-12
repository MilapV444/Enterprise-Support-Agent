"""M1-02: sessions end at 30 min idle / 12 h absolute; conversations outlive them and link to cases (FR-8)."""

import pytest

from channels import sessions
from tests.identity.conftest import connect, sql


def test_activity_keeps_a_session_alive_until_idle():
    with connect() as conn:
        sid = sessions.start(conn, "t_us", "sarah", "T1_VERIFIED")
        sql(f"UPDATE sessions SET last_seen_at = now() - interval '29 minutes' WHERE id = '{sid}'")
        assert sessions.touch(conn, "t_us", sid) == ("sarah", "T1_VERIFIED")
        sql(f"UPDATE sessions SET last_seen_at = now() - interval '31 minutes' WHERE id = '{sid}'")
        assert sessions.touch(conn, "t_us", sid) is None


def test_absolute_cap_ends_even_an_active_session():
    with connect() as conn:
        sid = sessions.start(conn, "t_us", "sarah", "T1_VERIFIED")
        sql(f"UPDATE sessions SET created_at = now() - interval '12 hours 1 minute' WHERE id = '{sid}'")
        assert sessions.touch(conn, "t_us", sid) is None


def test_ended_and_foreign_sessions_are_not_live():
    with connect() as conn:
        sid = sessions.start(conn, "t_us", "sarah", "T1_VERIFIED")
        assert sessions.touch(conn, "t_eu", sid) is None
        sessions.end(conn, "t_us", sid)
        assert sessions.touch(conn, "t_us", sid) is None


def test_conversation_outlives_its_session_and_stays_with_its_owner():
    with connect() as conn:
        first = sessions.start(conn, "t_us", "sarah", "T1_VERIFIED")
        assert sessions.open_conversation(conn, "t_us", "sarah", first, "conv-a")
        sessions.end(conn, "t_us", first)
        later = sessions.start(conn, "t_us", "sarah", "T1_VERIFIED")
        assert sessions.open_conversation(conn, "t_us", "sarah", later, "conv-a")
        intruder = sessions.start(conn, "t_us", "bob", "T1_VERIFIED")
        assert not sessions.open_conversation(conn, "t_us", "bob", intruder, "conv-a")


def test_several_conversations_link_to_one_case():
    with connect() as conn:
        sid = sessions.start(conn, "t_us", "sarah", "T1_VERIFIED")
        for conversation in ("conv-b", "conv-c"):
            sessions.open_conversation(conn, "t_us", "sarah", sid, conversation)
        case = sessions.link_case(conn, "t_us", "conv-b")
        assert sessions.link_case(conn, "t_us", "conv-c", case) == case
    linked = "SELECT count(*) FROM conversations WHERE case_id IS NOT NULL AND id IN ('conv-b', 'conv-c')"
    assert sql(linked) == [["2"]]


def test_a_case_of_another_tenant_cannot_be_linked():
    with connect() as conn:
        eu = sessions.start(conn, "t_eu", "eve", "T1_VERIFIED")
        sessions.open_conversation(conn, "t_eu", "eve", eu, "conv-eu")
        foreign_case = sessions.link_case(conn, "t_eu", "conv-eu")
        us = sessions.start(conn, "t_us", "sarah", "T1_VERIFIED")
        sessions.open_conversation(conn, "t_us", "sarah", us, "conv-d")
        with pytest.raises(LookupError, match="unknown case"):
            sessions.link_case(conn, "t_us", "conv-d", foreign_case)


def test_new_tables_enforce_row_level_security():
    rows = sql("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
               "WHERE relname IN ('sessions', 'conversations', 'cases', 'otp_challenges') ORDER BY relname")
    assert rows == [[name, "t", "t"] for name in ("cases", "conversations", "otp_challenges", "sessions")]
