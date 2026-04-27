"""Per-connection live session state and registry.

Mirrors the singleton-registry pattern used elsewhere in the codebase
(e.g. ``deeptutor.services.tutorbot.get_tutorbot_manager``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)

DEFAULT_TOPIC = "general"
DEFAULT_DIFFICULTY = 1


@dataclass
class LiveSession:
    """State for a single live voice WS connection."""

    session_id: str
    user_id: str
    websocket: "WebSocket"
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    conversation: list[dict[str, str]] = field(default_factory=list)
    topic: str = DEFAULT_TOPIC
    difficulty: int = DEFAULT_DIFFICULTY
    created_at: float = field(default_factory=time.time)


class SessionRegistry:
    """Thread-safe registry of active LiveSession instances.

    Enforces ``max-1-concurrent-session-per-user`` (rejects duplicates with
    close code 4003 at the router layer). Provides graceful drain via
    ``close_all()`` — used by the FastAPI lifespan shutdown handler.
    """

    def __init__(self) -> None:
        self._by_session_id: dict[str, LiveSession] = {}
        self._by_user_id: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def register(self, session: LiveSession) -> bool:
        """Register a session. Returns ``False`` if the user already has one."""
        async with self._lock:
            if session.user_id in self._by_user_id:
                return False
            self._by_session_id[session.session_id] = session
            self._by_user_id[session.user_id] = session.session_id
            return True

    async def deregister(self, session_id: str) -> None:
        async with self._lock:
            session = self._by_session_id.pop(session_id, None)
            if session is not None and self._by_user_id.get(session.user_id) == session_id:
                self._by_user_id.pop(session.user_id, None)

    def get(self, session_id: str) -> LiveSession | None:
        return self._by_session_id.get(session_id)

    def get_by_user(self, user_id: str) -> LiveSession | None:
        sid = self._by_user_id.get(user_id)
        return self._by_session_id.get(sid) if sid else None

    async def abort(self, session_id: str) -> None:
        session = self.get(session_id)
        if session is not None:
            session.abort_event.set()

    def __len__(self) -> int:
        return len(self._by_session_id)

    async def close_all(self, timeout: float = 5.0) -> None:
        """Notify and disconnect every active session.

        Called from the FastAPI lifespan shutdown handler. Sends a retryable
        error frame so clients can reconnect once the server returns.
        """
        async with self._lock:
            sessions = list(self._by_session_id.values())
            self._by_session_id.clear()
            self._by_user_id.clear()

        if not sessions:
            return

        logger.info("Closing %d live voice session(s) for shutdown", len(sessions))

        async def _close_one(session: LiveSession) -> None:
            session.abort_event.set()
            try:
                await session.websocket.send_json(
                    {
                        "type": "error",
                        "message": "Server restarting",
                        "retryable": True,
                    }
                )
            except Exception:
                pass
            try:
                await session.websocket.close(code=1012)
            except Exception:
                pass

        await asyncio.wait_for(
            asyncio.gather(*(_close_one(s) for s in sessions), return_exceptions=True),
            timeout=timeout,
        )


_registry: SessionRegistry | None = None


def get_session_registry() -> SessionRegistry:
    """Singleton accessor for the live session registry."""
    global _registry
    if _registry is None:
        _registry = SessionRegistry()
    return _registry
