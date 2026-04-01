import pytest

from agent.settings import SettingsManager


@pytest.fixture
def tmp_db_url(tmp_path):
    url = str(tmp_path / "sessions.db")
    SettingsManager.get_instance().set("persistence.url", url)
    return url


def test_upsert_and_fetch_session_messages_roundtrip(tmp_db_url):
    from agent.persistence.session_queries import (fetch_session_messages,
                                                   upsert_session_messages)

    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    upsert_session_messages("mgr", "worker", "sess-uuid-1", msgs)
    assert fetch_session_messages("mgr", "worker", "sess-uuid-1") == msgs

    updated = msgs + [{"role": "user", "content": "more"}]
    upsert_session_messages("mgr", "worker", "sess-uuid-1", updated)
    assert fetch_session_messages("mgr", "worker", "sess-uuid-1") == updated

    assert fetch_session_messages("other", "worker", "sess-uuid-1") is None
