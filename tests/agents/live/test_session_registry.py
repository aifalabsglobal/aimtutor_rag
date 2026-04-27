"""SessionRegistry concurrency rules."""

from __future__ import annotations

import pytest

from deeptutor.agents.live.session import LiveSession, SessionRegistry


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed: int | None = None

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:
        self.closed = code


def _make(session_id: str, user_id: str) -> LiveSession:
    return LiveSession(
        session_id=session_id, user_id=user_id, websocket=_FakeWebSocket()
    )


@pytest.mark.asyncio
async def test_register_rejects_second_session_for_same_user() -> None:
    reg = SessionRegistry()
    s1 = _make("s1", "alice")
    s2 = _make("s2", "alice")

    assert await reg.register(s1) is True
    assert await reg.register(s2) is False
    assert reg.get_by_user("alice") is s1
    assert len(reg) == 1


@pytest.mark.asyncio
async def test_deregister_clears_user_index() -> None:
    reg = SessionRegistry()
    s1 = _make("s1", "alice")
    await reg.register(s1)

    await reg.deregister("s1")
    assert reg.get("s1") is None
    assert reg.get_by_user("alice") is None

    s2 = _make("s2", "alice")
    assert await reg.register(s2) is True


@pytest.mark.asyncio
async def test_abort_sets_session_event() -> None:
    reg = SessionRegistry()
    session = _make("s1", "alice")
    await reg.register(session)

    assert not session.abort_event.is_set()
    await reg.abort("s1")
    assert session.abort_event.is_set()


@pytest.mark.asyncio
async def test_close_all_drains_and_notifies() -> None:
    reg = SessionRegistry()
    a = _make("s1", "alice")
    b = _make("s2", "bob")
    await reg.register(a)
    await reg.register(b)

    await reg.close_all(timeout=2.0)

    assert len(reg) == 0
    for session in (a, b):
        ws = session.websocket
        assert isinstance(ws, _FakeWebSocket)
        assert ws.closed == 1012
        assert any(
            frame.get("type") == "error" and frame.get("retryable") is True
            for frame in ws.sent
        )
        assert session.abort_event.is_set()
