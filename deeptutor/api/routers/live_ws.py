"""Live Voice Session WebSocket
==============================

Single full-duplex endpoint at ``/api/v1/ws/live`` for real-time voice
tutoring. This is a sibling to ``unified_ws.py`` (the chat-turn protocol);
it is kept in its own module because the wire protocol is fundamentally
different (transcript / token / sentence / interrupt frames).

Wire protocol — JSON over WebSocket
-----------------------------------

Client -> Server:
    {"type": "transcript", "text": str, "is_final": bool, "timestamp": int}
    {"type": "interrupt"}
    {"type": "pong"}

Server -> Client:
    {"type": "ready",    "session_id": str}
    {"type": "token",    "text": str, "index": int}
    {"type": "sentence", "text": str}
    {"type": "done",     "full_text": str, "ttft_ms": int}
    {"type": "meta",     "topic": str, "difficulty": int, "mastery": dict}
    {"type": "error",    "message": str, "retryable": bool}
    {"type": "ping"}

Close codes
-----------
    4001: Unauthorized (Clerk token rejected)
    4002: Idle timeout (no client traffic for HEARTBEAT_TIMEOUT_S)
    4003: Conflict (user already has an active live session)
    4004: Server error (uncaught exception)

Auth
----
    When Clerk is configured (server-side ``CLERK_SECRET_KEY`` set) the
    ``?token=...`` query parameter must be a valid Clerk session JWT.
    When Clerk is not configured the token string is treated as the user_id
    (parity with the frontend's ``isClerkPublishableConfigured()`` check).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from deeptutor.agents.live import (
    LiveSession,
    bkt_update,
    get_knowledge_store,
    get_session_registry,
    infer_correctness,
    is_clerk_configured,
    stream_live_response,
    topic_to_skill,
    verify_session_token,
    warmup_llm,
)
from deeptutor.agents.live.bkt import DEFAULT_MASTERY, DEFAULT_SKILL

logger = logging.getLogger(__name__)
router = APIRouter()

PING_INTERVAL_S = 30.0
HEARTBEAT_TIMEOUT_S = 75.0
MAX_TRANSCRIPT_CHARS = 500
MAX_HISTORY_MESSAGES = 16  # 8 user + 8 assistant turns

CLOSE_UNAUTHORIZED = 4001
CLOSE_TIMEOUT = 4002
CLOSE_CONFLICT = 4003
CLOSE_SERVER_ERROR = 4004


def _sanitize_transcript(text: Any) -> str:
    """Strip newlines, collapse whitespace, cap length to ``MAX_TRANSCRIPT_CHARS``."""
    if not isinstance(text, str):
        return ""
    cleaned = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return cleaned[:MAX_TRANSCRIPT_CHARS]


async def _resolve_user_id(token: str) -> str | None:
    """Resolve a connection token to a user id.

    - When Clerk is configured: verify as a Clerk session JWT.
    - Otherwise: treat the token string itself as the user_id (local dev).
    """
    if not token:
        return None
    if is_clerk_configured():
        return await verify_session_token(token)
    return token


@router.websocket("/ws/live")
async def live_session_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    """Full-duplex live voice tutoring endpoint."""
    user_id = await _resolve_user_id(token)
    if not user_id:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    registry = get_session_registry()
    if registry.get_by_user(user_id) is not None:
        await websocket.close(code=CLOSE_CONFLICT)
        return

    await websocket.accept()

    session = LiveSession(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        websocket=websocket,
    )
    registered = await registry.register(session)
    if not registered:
        await websocket.close(code=CLOSE_CONFLICT)
        return

    knowledge_store = get_knowledge_store()
    last_received_at = time.monotonic()
    ping_task: asyncio.Task[None] | None = None
    response_task: asyncio.Task[None] | None = None

    async def _safe_send(payload: dict[str, Any]) -> None:
        try:
            await websocket.send_json(payload)
        except Exception:
            pass

    async def _ping_loop() -> None:
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL_S)
                if time.monotonic() - last_received_at > HEARTBEAT_TIMEOUT_S:
                    try:
                        await websocket.close(code=CLOSE_TIMEOUT)
                    except Exception:
                        pass
                    return
                await _safe_send({"type": "ping"})
        except asyncio.CancelledError:
            return

    async def _handle_transcript(text: str) -> None:
        cleaned = _sanitize_transcript(text)
        if not cleaned:
            return

        session.abort_event.clear()
        session.conversation.append({"role": "user", "content": cleaned})
        if len(session.conversation) > MAX_HISTORY_MESSAGES:
            session.conversation = session.conversation[-MAX_HISTORY_MESSAGES:]

        mastery = await knowledge_store.get(session.user_id)

        full_text_parts: list[str] = []
        async for event in stream_live_response(
            session.conversation, mastery, session.abort_event
        ):
            if session.abort_event.is_set():
                break

            if event["type"] == "token":
                full_text_parts.append(str(event.get("text", "")))
            elif event["type"] == "done":
                # full_text from the pipeline already strips trailing whitespace.
                full_text_parts = [str(event.get("full_text", ""))]

            await _safe_send(event)

        if not full_text_parts:
            return

        final_text = "".join(full_text_parts).strip()
        if final_text:
            session.conversation.append({"role": "assistant", "content": final_text})

        skill = topic_to_skill(session.topic)
        prior = mastery.get(skill, mastery.get(DEFAULT_SKILL, DEFAULT_MASTERY))
        new_p = bkt_update(prior, infer_correctness(final_text))
        await knowledge_store.update_skill(session.user_id, skill, new_p)

        latest = await knowledge_store.get(session.user_id)
        await _safe_send(
            {
                "type": "meta",
                "topic": session.topic,
                "difficulty": session.difficulty,
                "mastery": latest,
            }
        )

    try:
        await _safe_send({"type": "ready", "session_id": session.session_id})
        ping_task = asyncio.create_task(_ping_loop())
        # Best-effort prewarm of the LLM HTTP pool — hides ~3-4 s of cold
        # TLS-handshake cost from the user's first transcript. Fire-and-forget.
        asyncio.create_task(warmup_llm())

        logger.info(
            "Live voice session opened: session_id=%s user=%s",
            session.session_id,
            session.user_id,
        )

        while True:
            raw = await websocket.receive_text()
            last_received_at = time.monotonic()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _safe_send(
                    {"type": "error", "message": "Invalid JSON", "retryable": False}
                )
                continue

            msg_type = msg.get("type")

            if msg_type == "transcript":
                if not bool(msg.get("is_final")):
                    continue
                text = msg.get("text", "")
                logger.info(
                    "live transcript: session_id=%s chars=%d",
                    session.session_id,
                    len(text) if isinstance(text, str) else 0,
                )

                if response_task and not response_task.done():
                    session.abort_event.set()
                    try:
                        await asyncio.wait_for(response_task, timeout=0.5)
                    except (asyncio.TimeoutError, Exception):
                        response_task.cancel()
                response_task = asyncio.create_task(_handle_transcript(text))
                continue

            if msg_type == "interrupt":
                session.abort_event.set()
                continue

            if msg_type == "pong":
                continue

            await _safe_send(
                {
                    "type": "error",
                    "message": f"Unknown frame type: {msg_type}",
                    "retryable": False,
                }
            )
    except WebSocketDisconnect:
        logger.info("Live voice session disconnected: session_id=%s", session.session_id)
    except Exception:
        logger.exception("Live voice session crashed: session_id=%s", session.session_id)
        try:
            await websocket.close(code=CLOSE_SERVER_ERROR)
        except Exception:
            pass
    finally:
        session.abort_event.set()
        if ping_task is not None:
            ping_task.cancel()
            try:
                await ping_task
            except (asyncio.CancelledError, Exception):
                pass
        if response_task is not None and not response_task.done():
            response_task.cancel()
            try:
                await response_task
            except (asyncio.CancelledError, Exception):
                pass
        await registry.deregister(session.session_id)
